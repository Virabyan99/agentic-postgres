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
| `THR-AGENT-SQL` | Full control of MCP tool inputs | The entire database beyond the agent's approved surface | Frozen resource, column, and operator allowlists; structured filters from a closed enum; no field accepts SQL, a fragment, or a query string | Capability/OpenAPI drift fails the smoke test; injection payloads appear in the audit log as data | A logic error inside an approved RPC is still reachable. The allowlist bounds the surface, not the correctness of what is on it | `AGT-SQL-001`, `SEC-INJ-001`, `AGT-DRIFT-001` | `tests/integration/test_future_mcp.py::test_no_tool_accepts_sql_or_a_raw_query_string` | 8 |
| `THR-CROSS-USER` | A valid credential for user A | User B's rows | PostgreSQL row-level security on every owned table, security-invoker views, narrow write RPCs | Denials surface as empty result sets and authorization errors, logged without token contents | A shared row deliberately visible to both users is out of scope for RLS by definition | `SEC-RLS-001`, `SEC-VIEW-001` | `tests/security/test_future_security_boundaries.py::test_user_a_cannot_access_user_b_rows` | 3 |
| `THR-PRIV-ESC` | Ability to call any exposed function | Ownership and grant hierarchy | Non-login object owner, fixed safe `search_path` on every `SECURITY DEFINER` function, revoked default `PUBLIC` execute, explicit per-role grants | Default-privilege and ungranted-function tests fail loudly on regression | A `SECURITY DEFINER` function with a logic flaw still runs as its owner. Ownership is constrained; correctness is not | `SEC-FUNC-001`, `SEC-DEFAULT-001`, `SEC-OWNER-001` | `tests/security/test_future_security_boundaries.py::test_api_role_cannot_execute_ungranted_functions` | 3 |
| `THR-SERVICE-COMPROMISE` | Code execution inside one runtime container | Everything that container's credentials reach | Distinct least-privilege role per boundary; no shared service role; no superuser or `BYPASSRLS` at runtime | Per-identity privilege tests assert each role's reachable surface | The compromised service's own legitimate surface is fully exposed. Segmentation limits blast radius, not the breach | `SEC-PRIV-001`, `SEC-ANON-001` | `tests/security/test_future_security_boundaries.py::test_api_roles_cannot_reach_the_private_schema` | 5 |
| `THR-JWT-FORGERY` | Full read access to a verifying service's configuration and mounted files | The ability to mint tokens for any identity | Asymmetric signing; the private key exists only in the auth service; verifiers receive public material | Secret-mount inspection; invalid algorithm and key tests | Compromise of the auth service itself yields signing capability. This is the trust root and is not further reducible in the MVP | `SEC-KEY-001`, `SEC-JWT-001` | `tests/security/test_future_security_boundaries.py::test_verifying_services_do_not_hold_the_private_signing_key` | 6 |
| `THR-SECRET-DISCLOSURE` | Read access to the repository, built images, logs, or process arguments | Every credential in the deployment | Docker secrets or tmpfs; no persistent production `.env`; redaction in logs; secrets never passed as command-line arguments | Repository, image, Compose-output, and log scans | A secret held in process memory is recoverable by anyone who can already read that process | `SEC-SECRET-001`, `CFG-009` | `tests/security/test_future_security_boundaries.py::test_secret_values_do_not_appear_in_images_logs_or_compose_output` | 2 |
| `THR-CROSS-PROJECT` | Full control of one project deployed on a shared host | A neighbouring project's data, credentials, and backups | Deterministic project-scoped namespacing of every network, volume, role, database, issuer, audience, secret namespace, bucket prefix, and backup stanza | Two-project isolation matrix; destructive-removal test | Host-level compromise defeats every project on the host. Isolation is project-scoped, not hypervisor-grade | `CFG-012`, `DEP-ISO-001`, `DEP-REMOVE-001` | `tests/contract/test_render_isolation.py::test_collision_count_is_zero` | 12 |
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
