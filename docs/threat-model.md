# Threat model

Every row maps a claimed security property to a control, a way to detect
failure, an explicitly accepted residual risk, and executable proof.

The table below is **hand-authored** — attacker capability and residual risk are
analysis, not derivable data. What *is* machine-checked is referential
integrity: `tests/contract/test_acceptance_registry.py` parses the
`Acceptance requirement IDs` and `Acceptance test node IDs` columns and fails if
either names something absent from `tests/acceptance-registry.yaml` or from a
real pytest collection. The analysis itself is not parsed.

The column headers are contract. Changing them breaks the parser, which is
intentional: a silently renamed column would turn the integrity check into a
no-op.

## Threats

| Threat ID | Attacker capability | Protected asset | Prevention | Detection | Residual risk | Acceptance requirement IDs | Acceptance test node IDs | Target session |
|---|---|---|---|---|---|---|---|---:|
| `THR-AGENT-TOKEN` | Holds a valid, unexpired agent access token obtained from a compromised client | Project data reachable by that agent's scopes | Short token expiry plus an authoritative active-agent check inside the PostgREST `db-pre-request` transaction | The audit log records every attempt with its request ID; denials are recorded, not dropped | Data the agent could legitimately read before revocation is already disclosed. Revocation limits future access, not past access | `SEC-REV-001`, `AGT-AUDIT-001` | `tests/security/test_future_security_boundaries.py::test_revoked_token_is_denied_by_mcp_and_postgrest` | 9 |
| `THR-AGENT-SQL` | Full control of MCP tool inputs | The entire database beyond the agent's approved surface | Frozen resource, column, and operator allowlists; structured filters from a closed enum; no field accepts SQL, a fragment, or a query string | Capability/OpenAPI drift fails the smoke test; injection payloads appear in the audit log as data | A logic error inside an approved RPC is still reachable. The allowlist bounds the surface, not the correctness of what is on it | `AGT-SQL-001`, `SEC-INJ-001`, `AGT-DRIFT-001` | `tests/contract/test_mcp_tools.py::test_no_tool_input_accepts_sql_a_fragment_or_a_query_string`, `tests/security/test_session8_agent_injection.py::test_a_payload_in_a_filter_value_does_not_change_the_request_structure` | 8 |
| `THR-CROSS-USER` | A valid credential for user A | User B's rows | PostgreSQL row-level security on every owned table, security-invoker views, narrow write RPCs | Denials surface as empty result sets and authorization errors, logged without token contents | A shared row deliberately visible to both users is out of scope for RLS by definition | `SEC-RLS-001`, `SEC-VIEW-001` | `tests/security/test_session3_authorization.py::test_user_a_cannot_read_user_b_rows` | 3 |
| `THR-PRIV-ESC` | Ability to call any exposed function | Ownership and grant hierarchy | Non-login object owner, fixed safe `search_path` on every `SECURITY DEFINER` function, revoked default `PUBLIC` execute, explicit per-role grants | Default-privilege and ungranted-function tests fail loudly on regression | A `SECURITY DEFINER` function with a logic flaw still runs as its owner. Ownership is constrained; correctness is not | `SEC-FUNC-001`, `SEC-DEFAULT-001`, `SEC-OWNER-001` | `tests/security/test_session3_authorization.py::test_an_api_role_cannot_execute_an_ungranted_function` | 3 |
| `THR-SERVICE-COMPROMISE` | Code execution inside one runtime container | Everything that container's credentials reach | Distinct least-privilege role per boundary; no shared service role; no superuser or `BYPASSRLS` at runtime | Per-identity privilege tests assert each role's reachable surface | The compromised service's own legitimate surface is fully exposed. Segmentation limits blast radius, not the breach | `SEC-PRIV-001`, `SEC-ANON-001` | `tests/deployment/test_session5_api_authorization.py::test_the_private_schemas_are_unreachable_through_postgrest` | 5 |
| `THR-JWT-FORGERY` | Full read access to a verifying service's configuration and mounted files | The ability to mint tokens for any identity | Asymmetric signing; the private key exists only in the auth service; verifiers receive public material | Secret-mount inspection; invalid algorithm and key tests | Compromise of the auth service itself yields signing capability. This is the trust root and is not further reducible in the MVP | `SEC-KEY-001`, `SEC-JWT-001` | `tests/deployment/test_session6_tokens.py::test_no_verifier_holds_private_signing_material`, `tests/deployment/test_session6_tokens.py::test_both_verifiers_refuse_the_same_bad_tokens` | 6 |
| `THR-SECRET-DISCLOSURE` | Read access to the repository, built images, logs, or process arguments | Every credential in the deployment | Individual secret files in immutable generations, owned by the consuming UID; no persistent production `.env`; redaction in logs; secrets never passed as command-line arguments | Repository, image, `docker inspect`, Compose-output, journal, and container-log scans for a real sentinel value | A secret held in process memory is recoverable by anyone who can already read that process. Secret-zero — the control-plane credential and one per-project client secret — still lives on the host, root-only | `SEC-SECRET-001`, `SEC-SECRET-002`, `CFG-009` | `tests/security/test_session2_secrets.py::test_the_sentinel_is_absent_from_image_history`, `tests/security/test_session2_secret_model.py::test_no_service_takes_a_secret_through_the_environment` | 2 |
| `THR-PUBLIC-INGRESS` | Can reach the host's public addresses from any network | Every service port that is not meant to be public | Only the edge publishes a host port; a `DOCKER-USER` policy matching the pre-DNAT destination port drops forwarded traffic to anything else; UFW defaults to deny incoming | Full-TCP connect scan from an unrelated network, with 443 as the positive control; live comparison of the running chain against the installed policy | A published port added later is covered only if the firewall policy is re-reconciled. The `DOCKER-USER` chain protects forwarded traffic, not processes bound directly on the host | `SEC-NET-001`, `SEC-NET-002`, `SEC-HOST-001` | `tests/external/test_session2_public_edge.py::test_no_service_port_is_publicly_reachable_over_ipv4`, `tests/deployment/test_session2_host.py::test_the_docker_user_chain_matches_the_original_destination_port` | 2 |
| `THR-EDGE-DAEMON` | Code execution inside the publicly reachable reverse proxy | The Docker daemon, and therefore every container and the host | Traefik holds no Docker socket; it reads the API through a proxy whose allowlist enables five read sections and denies everything else, on an internal-only network; the daemon listens on no TCP socket | A live probe on the control network asserting a permitted read returns 200 and a container-create returns 403 | A read-only view of the Docker API still discloses container names, labels, and network topology to a compromised proxy | `SEC-DOCKER-001` | `tests/deployment/test_session2_host.py::test_the_socket_proxy_refuses_a_write_call`, `tests/contract/test_compose_contract.py::test_the_socket_proxy_denies_every_unneeded_api_section` | 2 |
| `THR-EDGE-LOGGING` | Read access to the edge access log, by operator error or log shipping | Bearer tokens and credentials carried in request headers and query strings | Traefik drops query parameters and all headers by default, keeping two by name | A request carrying a random sentinel in both a query parameter and a header, followed by a search of the log, with a positive control proving the log is recording those requests | Anything a client puts in a *path* is still logged. Paths are not a credential channel by convention, not by enforcement | `SEC-LOG-001` | `tests/deployment/test_session2_edge.py::test_no_query_string_reaches_the_access_log` | 2 |
| `THR-CHECKOUT-SWAP` | Write access to the operator's clone on the deployment host | What runs at the next boot or restart | systemd units execute only `/usr/local/libexec` launchers, which resolve a root-owned immutable release under `/opt/agentic-postgres/releases/{commit}`; the checkout is a transport artifact and is never executed | Every `Exec*` line of every installed unit is asserted to point into libexec; the release is asserted root-owned, non-group-writable, and free of `.git` | Root on the host can replace the release. This bounds what a non-root operator edit can change, not what root can | `DEP-REL-001` | `tests/security/test_session2_installed_release.py::test_the_installed_unit_executes_only_a_libexec_launcher` | 2 |
| `THR-CROSS-PROJECT` | Full control of one project deployed on a shared host | A neighbouring project's data, credentials, and backups | Deterministic project-scoped namespacing of every network, volume, role, database, issuer, audience, secret namespace, bucket prefix, and backup stanza | Two-project isolation matrix; destructive-removal test | Host-level compromise defeats every project on the host. Isolation is project-scoped, not hypervisor-grade | `CFG-012`, `DEP-ISO-001`, `DEP-ISO-002`, `DEP-REMOVE-001` | `tests/contract/test_render_isolation.py::test_collision_count_is_zero`, `tests/deployment/test_session2_isolation.py::test_neither_hostname_serves_the_other_project` | 12 |
| `THR-DATA-LOSS` | None — this is node loss or operator error, not an adversary | Availability and durability of project data | Encrypted pgBackRest repository, continuous WAL archiving, retained full-backup chains | Backup and WAL archive failures produce a non-zero operational signal | Data written after the last archived WAL segment is unrecoverable. The window is bounded by archive frequency, not eliminated | `REC-PITR-001`, `REC-SMOKE-001`, `REC-WAL-001` | `tests/recovery/test_future_pitr.py::test_timestamp_targeted_restore_succeeds` | 10 |
| `THR-BACKUP-COMPROMISE` | Read access to the backup repository credentials | Every historical copy of the database | Backup credentials separate from application credentials; repository encryption key stored separately from repository credentials; application services hold neither | Credential-scope checks assert application services cannot reach the backup bucket | Backups in the same provider account do not survive account-level compromise. This is documented in operations guidance and explicitly accepted for the MVP | `REC-EVID-001`, `SEC-SECRET-001` | `tests/recovery/test_future_pitr.py::test_restore_evidence_records_the_required_fields` | 10 |

## Notes on residual risk

Three of these are worth restating outside the table, because they are the ones
most likely to be misread as "handled":

**Revocation is forward-looking.** `SEC-REV-001` proves a token stops working on
its next request. It does not un-disclose anything the agent already read. If
disclosure matters more than continued access, revocation is not the control —
scope reduction before issuance is.

**The backup account boundary is not a disaster-recovery boundary.** Backups
stored in the same provider account as the application protect against node
loss and operator error. They do not protect against compromise of that account.
Source specification §12.2 states this and the MVP accepts it; an independent
backup account is listed as post-MVP work.

**Allowlists bound the surface, not the correctness of what is on it.** Every
agent-facing control here constrains *which* operations are reachable. None of
them makes an approved operation correct. A flawed RPC on the allowlist is
reachable by design.

## Scope

This model covers the deployed system. It deliberately excludes:

- Physical and hypervisor-level attacks on the host.
- Compromise of the container registry or the base images themselves; that is
  mitigated separately by digest pinning (`CFG-014`), which proves you got the
  bytes you asked for, not that those bytes are trustworthy.
- Supply-chain compromise of a locked Python dependency.
- Denial of service. Rate limiting is a protective control here, not an
  authorization control, and no availability SLA is claimed.
