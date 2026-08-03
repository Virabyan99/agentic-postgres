# Agentic Postgres Primitive — MVP Technical & Functional Specification

**Status:** implementation candidate — external-assessment changes integrated  
**Delivery constraint:** 12 high-intensity coding sessions, 8–12 hours each  
**Deployment model:** one project per isolated deployment on one VPS  
**Product shape:** reusable deployable primitive/template, not a managed multi-tenant platform

---

## 1. Product Contract

### 1.1 What this MVP is

A self-hosted, project-scoped PostgreSQL capability appliance that gives an application team:

1. A standard PostgreSQL connection for normal application frameworks and ORMs.
2. A stable REST API backed by PostgreSQL views and functions.
3. A small custom application API for authentication, storage, and non-SQL business logic.
4. A curated MCP interface for AI agents, with explicit capabilities, attribution, revocation, limits, and auditability.
5. Automated TLS, secrets injection, backups, restore tooling, and repeatable deployment.

The primitive must be reusable by another team member without editing infrastructure source files. Project-specific database objects and agent tools are added through migrations and a small project manifest.

### 1.2 What “close to Neon and Prisma Postgres” means for this MVP

The MVP targets the low-effort developer-experience features that are feasible on a single VPS:

- Fast project provisioning from a template.
- Standard pooled and direct PostgreSQL connection strings.
- Compatibility with Prisma ORM and ordinary PostgreSQL drivers.
- PostgreSQL extensions, including pgvector.
- Automated backups and tested point-in-time recovery.
- Stable API contracts and generated documentation.
- Isolated project deployments.
- Clear operational commands and example clients.

It does **not** attempt to reproduce storage/compute separation, autoscaling, scale-to-zero, instant copy-on-write branches, multi-region durability, global edge caching, or a shared managed control plane.

### 1.3 MVP success criterion

At the end of session 12, a developer who did not build the primitive must be able to:

1. Clone the repository.
2. Fill in one project manifest and the required provider bootstrap credentials.
3. Run one documented deployment command.
4. Receive working pooled and direct database URLs, REST/API URLs, an MCP URL, and admin bootstrap instructions.
5. Run a Prisma migration through the direct URL and application queries through the pooled URL.
6. Register an agent, call read and write tools, observe the audit trail, revoke the agent, and see its existing access token rejected on the next request.
7. Restore the database to a chosen point in time in a disposable volume.
8. Deploy a second isolated project on the same host without editing the first project’s configuration.

### 1.4 New team member happy path

A new team member should need no undocumented infrastructure knowledge. The documented path must remain fewer than 15 operator steps:

1. Obtain VPS SSH access and the approved provider-bootstrap credentials.
2. Clone the repository.
3. Copy `project.example.yaml` to `project.yaml`.
4. Set the project slug, environment, domain, and optional feature flags.
5. Review `capabilities.yaml` and enable only existing approved API operations.
6. Run `bin/bootstrap-providers.sh project.yaml` once for project-scoped external resources.
7. Run `./deploy.sh project.yaml`.
8. Read the non-secret deployment summary and machine-readable `outputs.json`.
9. Use `bin/connect.sh psql` to verify the direct database path.
10. Run the documented Prisma migration and pooled-client example.
11. Create a user and agent through documented admin commands.
12. Exercise REST and MCP read/write flows, inspect the audit log, and revoke the agent.
13. Run `bin/doctor.sh` and the acceptance suite.
14. Run the disposable restore drill and inspect its evidence file.

Completion means the developer reaches the success criterion in section 1.3 without source-file edits or undocumented commands.

---

## 2. Scope Priorities

### 2.1 Must-have capabilities

| Priority | Capability |
|---|---|
| P0 | Isolated, repeatable project deployment |
| P0 | Pooled PostgreSQL URL for application traffic |
| P0 | Direct PostgreSQL URL for migrations/admin through a restricted path |
| P0 | PostgREST over a stable `api` schema |
| P0 | RLS-safe views and narrow write functions |
| P0 | Short-lived JWT access tokens with issuer/audience validation |
| P0 | Agent credentials, scopes, audit trail, and immediate per-agent revocation |
| P0 | FastMCP tools that never accept arbitrary SQL |
| P0 | Backup, WAL archiving, PITR, and an exercised restore procedure |
| P1 | R2 presigned object upload/download with ownership metadata |
| P1 | Generated API documentation and example clients |
| P1 | Basic operational diagnostics, log correlation, and disk/WAL checks |
| P2 | pgvector example and vector search RPC |
| P2 | Portable nightly `pg_dump` export |

P2 items may be dropped before any P0 item if the schedule slips.

### 2.2 Explicit non-goals

- Database branching or copy-on-write clones.
- Autoscaling or scale-to-zero.
- High availability or automatic failover.
- Multi-region storage or global edge distribution.
- Zero-downtime major-version upgrades.
- Shared multi-tenant control plane.
- Public self-registration, email flows, OAuth, SSO, MFA, or account recovery.
- Arbitrary SQL execution by agents.
- Automatic schema mutation by agents.
- Generic natural-language-to-SQL execution.
- Full observability platform, on-call automation, or formal SLA.
- Complete object lifecycle synchronization between PostgreSQL and R2.

---

## 3. Actors

| Actor | Description |
|---|---|
| Platform operator | Controls the VPS, DNS, provider credentials, deployment, backups, and restores |
| Project admin | Creates users and agents, rotates credentials, reads audit records, and revokes access |
| Human application user | Authenticates and accesses rows allowed by RLS |
| Application service | Connects through PostgreSQL, PostgREST, or FastAPI using project-scoped credentials |
| AI agent | An MCP client calling a curated set of tools with a dedicated agent identity and scopes |
| Migration process | Uses the restricted direct PostgreSQL path and a dedicated migration role |
| Backup process | Archives WAL and executes backups with dedicated storage credentials |

---

## 4. Architecture Principles

1. **PostgreSQL remains the authorization source of truth for data access.**
2. **Every public data contract is defined in the `api` schema.** Base tables are never exposed directly.
3. **FastMCP is a protocol adapter and capability boundary, not an alternate authorization path.** Agent tools call the same protected REST/RPC surface used elsewhere, forwarding the agent token.
4. **Every agent request is checked twice:** once by FastMCP middleware for tool visibility and early rejection, and once inside the database request path before data access.
5. **No service receives PostgreSQL superuser credentials at runtime.**
6. **No generic service role is shared across FastAPI, FastMCP, migrations, and backups.** Each boundary receives the minimum grants it requires.
7. **Configuration is declarative.** A project manifest is the non-secret source of truth; secrets are injected separately.
8. **Security guarantees are executable.** Each guarantee has an automated negative test.
9. **Recovery is a feature only when restore has been demonstrated.**
10. **The template is optimized for comprehensibility and reuse, not maximal automation.**

### 4.1 Threat-model summary

The detailed security tests are the executable source of truth. This matrix defines the minimum threats the design claims to address:

| Threat or failure | Primary control | Detection or proof |
|---|---|---|
| Stolen or compromised agent access token | Short expiry plus authoritative active-agent check in PostgREST `db-pre-request` | Same pre-revocation token is denied through MCP and direct PostgREST immediately after revocation |
| Agent capability expansion into arbitrary SQL | Frozen operation/resource/column allowlists; structured operators; no SQL or raw query strings | Capability/OpenAPI drift test and injection/negative tests |
| Cross-user or cross-tenant data access | PostgreSQL RLS, security-invoker views, narrow RPCs | User A/User B isolation tests through SQL, REST, and MCP |
| Privilege escalation through functions or object ownership | Non-login owners, safe `search_path`, revoked default grants, explicit execution grants | Default-privilege and ungranted-function tests |
| Compromise of one runtime service | Distinct least-privilege service roles and secret mounts | Direct privilege tests for each service identity |
| JWT forgery by a verifier | Asymmetric signing; private key only in auth service | Secret-mount inspection and invalid-key/algorithm tests |
| Secret disclosure through files, logs, diagnostics, or process arguments | Docker secrets/tmpfs, strict permissions, redaction, no persistent production `.env` | Repository/image/Compose/log/verbose-command scans |
| Cross-project leakage on a shared host | Namespaced state, credentials, routes, issuers, audiences, buckets/prefixes, and backup stanzas | Two-project isolation matrix and destructive-removal test |
| Database/node loss or operator error | Encrypted backups, continuous WAL archiving, disposable PITR | Timestamp-targeted restore plus application smoke tests and evidence artifact |
| Backup repository compromise | Separate credentials and encryption key; no application-service access | Credential-scope checks and documented residual account-level risk |

---

## 5. Project Manifest and Repository Contract

### 5.1 Project manifest

Each deployment uses `project.yaml`:

```yaml
project:
  slug: example
  environment: dev
  domain: db.example.com

database:
  name: example_dev
  pooled_public: false
  max_client_connections: 100
  pool_size: 20

api:
  public_base_path: /api
  max_rows: 500

mcp:
  public_base_path: /mcp
  max_result_rows: 100
  max_response_bytes: 262144

storage:
  enabled: true
  bucket: example-dev
  upload_url_ttl_seconds: 600
  download_url_ttl_seconds: 300
  max_upload_bytes: 26214400

backup:
  enabled: true
  stanza: example-dev
  retain_full: 2
```

The manifest must not contain secret values.

### 5.2 Generated outputs

Deployment renders both a human-readable summary and a machine-readable `outputs.json`. The JSON file is the automation contract and must not require parsing terminal output. When it contains credential-bearing connection strings, it must be written with owner-only permissions (`0600`) and excluded from source control.

Deployment renders, at minimum:

- Docker Compose project name and network names.
- Database, role, and volume names.
- Service routes and hostnames.
- PostgreSQL pooled and direct connection strings.
- PostgREST, FastAPI, FastMCP, and documentation URLs.
- R2 bucket/prefix names.
- JWT issuer and audience values.
- Backup stanza and repository prefix.
- Enabled capability names and their resolved API operations.
- Deployment timestamp, template version, and locked component versions.

`outputs.json` must distinguish non-secret endpoint metadata from secret-bearing connection values and must never contain raw passwords, private signing keys, agent secrets, provider-bootstrap tokens, or presigned URLs.

### 5.3 Repository layout

```text
/
  project.example.yaml
  capabilities.example.yaml
  compose.yaml
  deploy.sh
  bin/
    bootstrap-providers.sh
    migrate.sh
    connect.sh
    smoke-test.sh
    restore-test.sh
    doctor.sh
  migrations/
    0001_roles.sql
    0002_schemas.sql
    0003_auth.sql
    0004_example_app.sql
    0005_api.sql
    0006_agent.sql
    0007_storage.sql
  services/
    auth-api/
    mcp/
    docs/
  tests/
    security/
    contract/
    integration/
    recovery/
  evidence/
  pytest.ini
  requirements-dev.txt
  versions.env
  README.md
```

Container image repositories, tags, digests, and resolved application versions must be pinned in `versions.env` or a generated lock file from session 1. A release candidate may not depend on floating tags.

### 5.4 Frozen example domain

The core migrations use one deliberately small example domain:

- `notes`: owner-scoped title/content records.
- `tasks`: owner-scoped records with a bounded status transition.
- ownership through the authenticated human-user identifier.
- optional attachment reference to an object-storage metadata row.

This domain is used consistently for RLS, views, RPCs, REST examples, MCP tools, Prisma compatibility, backup fixtures, and restore smoke tests. pgvector data and additional project tables are optional migrations and must not expand the P0 core domain.

### 5.5 Capability contract

Agent capabilities are declared in `capabilities.yaml`, separate from general deployment configuration. The file may contain only:

- Stable MCP tool name and description.
- Required scopes.
- Reference to one existing PostgREST operation or FastAPI endpoint.
- Approved resource, column, filter, order, row, timeout, and response-size limits.
- Audit-redaction metadata.

It may not contain SQL, SQL fragments, raw PostgREST query strings, ad-hoc columns absent from OpenAPI, or dynamic operation names.

PostgREST OpenAPI may be used during build or deployment to generate repetitive FastMCP schemas and wrappers, but it is never the authorization source and never implicitly publishes operations. The frozen allowlist is authoritative. Deployment fails when an enabled capability does not match the live API contract, and contract tests fail when relevant OpenAPI drift is not acknowledged in `capabilities.yaml`.

---

## 6. PostgreSQL Schema Design

### 6.1 Schemas

| Schema | Purpose |
|---|---|
| `api` | Only schema exposed through PostgREST; stable views and RPC functions |
| `app` | Project application tables; never directly exposed |
| `app_private` | Users, credentials, agents, audit records, object metadata, and internal helpers |
| `extensions` | pgvector and other extensions |

The `public` schema must not be writable by untrusted roles and must not contain application objects.

### 6.2 Core private tables

#### `app_private.users`

- `id`
- `username` or `email`
- `display_name`
- `status`: `active | disabled`
- `created_at`
- `updated_at`

#### `app_private.user_credentials`

- `user_id`
- `password_hash`
- `password_changed_at`
- `failed_attempts`
- `locked_until`

Passwords are stored only as modern password hashes. Raw passwords are never logged.

#### `app_private.agents`

- `id`
- `name`
- `status`: `active | revoked`
- `scopes text[]`
- `created_by`
- `created_at`
- `revoked_at`
- `last_used_at`

#### `app_private.agent_credentials`

- `id`
- `agent_id`
- `secret_prefix`
- `secret_hash`
- `created_at`
- `expires_at`
- `last_used_at`
- `revoked_at`

An agent secret is shown once. Only its hash and a non-secret prefix are stored.

#### `app_private.agent_tool_calls`

- `id`
- `request_id`
- `agent_id`
- `token_jti`
- `tool_name`
- `parameters_redacted jsonb`
- `status`: `started | succeeded | failed | denied`
- `row_count`
- `duration_ms`
- `error_code`
- `error_message_redacted`
- `started_at`
- `completed_at`

The log records all agent tool attempts, including reads, writes, denials, and failures. Tokens, passwords, presigned URLs, object contents, and unrestricted user data must never be stored in the audit payload.

#### `app_private.objects`

- `id`
- `bucket`
- `object_key`
- `owner_id`
- `status`: `pending | available | deleted | failed`
- `content_type`
- `expected_size`
- `actual_size`
- `etag`
- `checksum`
- `created_at`
- `uploaded_at`
- `deleted_at`

Object keys are generated server-side. The client does not choose an unrestricted R2 key.

### 6.3 Migration contract

`dbmate` is the canonical migration engine for the primitive. Platform migrations remain plain SQL so they can define PostgreSQL roles, schemas, extensions, RLS policies, grants, functions, triggers, comments, and PostgREST-specific objects without coupling the appliance to an application framework.

Requirements:

- `bin/migrate.sh` wraps the pinned `dbmate` version and chooses the direct URL.
- Migrations are ordered, immutable after release, transactional where PostgreSQL permits, and recorded in dbmate’s migration table.
- Prisma Migrate is a compatibility workflow for consuming projects, not the owner of the primitive’s platform schema.
- Every migration that changes the `api` contract triggers the PostgREST schema-cache reload and an OpenAPI contract check.
- Roll-forward/fix-forward migrations are preferred over editing an applied migration.

### 6.4 Schema security requirements

- Revoke `CREATE` on `public` from `PUBLIC`.
- Revoke default `EXECUTE` on newly created functions from `PUBLIC`.
- Use a dedicated object-owner role that is not used by public services.
- Enable RLS on every tenant/user-owned table.
- Use `FORCE ROW LEVEL SECURITY` where owner bypass would invalidate tests or guarantees.
- Define all exposed views with `security_invoker = true` unless a documented, tested exception is required.
- Give API roles only the underlying privileges required by security-invoker views.
- Every `SECURITY DEFINER` function must:
  - have a fixed safe `search_path`;
  - schema-qualify referenced objects;
  - validate caller identity and scope;
  - validate row-count or operation bounds;
  - be owned by a non-login owner role;
  - have `PUBLIC` execution revoked;
  - be granted only to the intended role.
- Migrations must reload the PostgREST schema cache after API DDL changes.

---

## 7. PostgreSQL Roles and Connections

### 7.1 Group roles (`NOLOGIN`)

| Role | Purpose |
|---|---|
| `anon` | Unauthenticated REST access; normally no data access |
| `authenticated` | Human-user data access subject to RLS |
| `agent_reader` | Execute approved read RPCs and select approved API views |
| `agent_writer` | Execute specifically granted write RPCs |
| `project_admin` | Project administration through restricted functions |

### 7.2 Login/service roles

| Role | Purpose |
|---|---|
| `postgrest_authenticator` | PostgREST connection role; may switch only to approved group roles |
| `auth_service` | Read/write only the credential and token records needed by the auth API |
| `mcp_audit_service` | Insert/update agent tool-call audit records; no application-table access |
| `storage_service` | Manage object metadata through narrow private functions |
| `migration_user` | Own/apply migrations through the restricted direct endpoint |
| `backup_user` | Permissions required for backup tooling; not used by applications |
| `app_runtime` | Optional ordinary PostgreSQL application role, RLS-scoped and project-specific |

No runtime service role may be a superuser or have unrestricted `BYPASSRLS`.

### 7.3 Connection endpoints

The deployment emits two database URLs:

1. **Pooled URL** — PgBouncer transaction pooling for application traffic.
2. **Direct URL** — PostgreSQL for migrations, administration, and operations that are incompatible with transaction pooling.

Default network policy:

- Pooled and direct endpoints are private to the Docker network.
- Remote team access uses an SSH tunnel or private overlay network.
- An opt-in `pooled_public` deployment profile may expose only PgBouncer with TLS, SCRAM authentication, connection limits, and an IP allowlist.
- Direct PostgreSQL is never publicly exposed by the template.

### 7.4 Developer connection helper

`bin/connect.sh` provides the supported local access workflow so developers do not manually assemble SSH tunnels or connection flags. At minimum it supports:

```text
bin/connect.sh tunnel
bin/connect.sh psql
bin/connect.sh prisma-studio
bin/connect.sh print-env
```

The command reads `outputs.json`, selects the direct or pooled endpoint appropriately, establishes and cleans up the restricted tunnel, avoids printing passwords by default, and exits non-zero when required tooling or access is unavailable.

### 7.5 PgBouncer requirements

- Transaction pool mode for application traffic.
- Explicit pool and queue limits.
- Prepared-statement behavior configured and tested with the selected PgBouncer version.
- Migrations and administrative tools use the direct URL.
- Integration tests cover Prisma Client through the pooled URL and Prisma Migrate through the direct URL.

---

## 8. Authentication and Token Model

### 8.1 Signing model

Use asymmetric JWT signing:

- The auth service holds the private signing key.
- PostgREST and FastMCP receive only public verification material.
- Public keys are exposed as a project-scoped JWKS document or mounted as a read-only JWKS file.
- Key IDs permit later key rotation.

### 8.2 Required access-token claims

- `iss` — project token issuer
- `aud` — project resource audience
- `sub` — human or agent identifier
- `role` — PostgreSQL role selected by PostgREST
- `scope` — explicit capability strings
- `agent_id` — agent tokens only
- `token_use` — `access`
- `jti` — unique token identifier
- `iat`
- `nbf`
- `exp`

All token-verifying services must validate signature, permitted algorithm, issuer, audience, token use, and expiration.

### 8.3 Human authentication

`POST /auth/login` exchanges admin-created credentials for a short-lived access token.

For MVP simplicity, human refresh tokens are not required. Users re-authenticate when the token expires. Refresh-token rotation may be added only after all P0 acceptance tests pass.

### 8.4 Agent authentication

1. Admin registers an agent and receives a one-time opaque agent secret.
2. `POST /auth/agent-token` exchanges the secret for a short-lived JWT.
3. The auth service derives `role` and `scope` from the current agent record; the client cannot request broader privileges.
4. Revoking the agent invalidates future token exchanges and causes existing access tokens to fail the active-agent check on their next request.

### 8.5 Kill-switch enforcement

The active-agent check must apply to every MCP tool call and every PostgREST request made with an agent token.

Enforcement flow:

1. FastMCP validates JWT signature and claims.
2. FastMCP checks agent status before listing or executing tools.
3. FastMCP forwards the same bearer token to PostgREST/FastAPI.
4. PostgREST `db-pre-request` validates the `agent_id` and status inside the request transaction.
5. Write RPCs derive agent identity from trusted request claims, never from an agent-supplied function parameter.

A revocation acceptance test must reuse a token issued before revocation and prove that the next read and write request are both denied.

---

## 9. API Surface

### 9.1 Public route layout

| Route | Service | Purpose |
|---|---|---|
| `/api/rest/*` | PostgREST | Stable REST-over-PostgreSQL API |
| `/api/app/*` | FastAPI | Authentication, administration, storage, and custom logic |
| `/mcp` | FastMCP | Remote MCP transport |
| `/docs` | Documentation service | Admin-protected documentation index |
| `/health/*` | Respective services | Liveness/readiness endpoints |

Exact prefixes may differ, but they must be generated from the project manifest and remain stable after deployment.

### 9.2 FastAPI endpoints

| Endpoint | Purpose |
|---|---|
| `POST /auth/login` | Human credentials to short-lived access token |
| `POST /auth/agent-token` | Agent secret to short-lived access token |
| `GET /auth/me` | Return validated identity, role, scopes, and token metadata |
| `POST /admin/users` | Create a human user |
| `PATCH /admin/users/{id}` | Enable/disable a user and reset credentials |
| `POST /admin/agents` | Create an agent and return its secret once |
| `POST /admin/agents/{id}/rotate-secret` | Rotate the agent credential |
| `PATCH /admin/agents/{id}` | Change status and scopes |
| `GET /admin/agent-tool-calls` | Paginated audit-log query |
| `POST /storage/upload-intents` | Create pending object metadata and a presigned upload URL |
| `POST /storage/upload-intents/{id}/complete` | Verify the object with R2 and mark metadata available |
| `GET /storage/objects/{id}/download-url` | Authorize ownership and issue a short-lived download URL |
| `DELETE /storage/objects/{id}` | Delete or tombstone an object |

Admin endpoints require explicit admin scope; a token role name alone is insufficient.

### 9.3 PostgREST surface

- Only the `api` schema is exposed.
- Read resources are security-invoker views or table-returning functions.
- Writes are narrow named functions.
- The global row-return limit is configured.
- Write functions include operation-specific affected-row limits.
- SQL comments provide summaries and descriptions for generated OpenAPI.
- Base schemas are not included in `db-schemas` and are not granted to API roles beyond what security-invoker views require.

### 9.4 Documentation

For MVP, serve:

1. A Scalar page for FastAPI OpenAPI.
2. A Scalar page for PostgREST OpenAPI generated with a dedicated documentation role.
3. A small authenticated index linking both surfaces and the MCP tool catalog.

Merging the specifications into one document is a stretch goal, not a blocker.

---

## 10. FastMCP Capability Model

### 10.1 Design rule

FastMCP must not connect with a broad database role and must not implement a second independent authorization model. Tools call protected PostgREST or FastAPI endpoints and forward the caller’s bearer token.

### 10.2 Core read tools

| Tool | Behavior |
|---|---|
| `list_resources` | Return only API resources visible to the caller |
| `describe_resource` | Return columns, descriptions, filterability, limits, and relationships for one API resource |
| `query_resource` | Structured read against an allowlisted resource with explicit select/filter/order/limit fields; no raw SQL or raw query-string passthrough |
| `run_report` | Execute one named, parameterized report RPC |
| `search_embeddings` | Optional pgvector RPC accepting an embedding and bounded match count |

`query_resource` requirements:

- Resource allowlist.
- Column allowlist derived from the API contract.
- Structured operators from a small enum.
- Maximum limit enforced by the server, independent of client input.
- Request timeout and maximum response bytes.
- No unrestricted joins, computed SQL fragments, function names, or arbitrary ordering expressions.

A natural-language `search_documents(query_text)` tool is not a core requirement unless an embedding provider and ingestion path are explicitly configured. pgvector installation alone does not imply an embedding service.

### 10.3 Write tools

Write tools are project-specific and individually named, for example:

- `create_note`
- `update_task_status`
- `attach_object`

Each tool maps one-to-one to a narrow API endpoint or SQL function. There is no `execute_sql`, `run_query`, generic mutation dispatcher, or schema-changing tool.

Each write capability declares:

- Required scope.
- Input schema and validation constraints.
- Whether it is idempotent.
- Expected side effect.
- Maximum rows affected.
- Redacted audit representation.

### 10.4 Tool registration

`capabilities.yaml` lists enabled project-specific tools and their backing operations. The general `project.yaml` does not define data capabilities.

FastMCP may read the PostgREST OpenAPI document during build or deployment to generate input/output schemas and repetitive wrapper code. Generation remains constrained by these rules:

- Only operations explicitly listed in `capabilities.yaml` are registered.
- Read-resource and column allowlists are frozen deployment artifacts, not discovered dynamically per request.
- Every write tool maps one-to-one to one named API operation.
- No newly added view, function, or endpoint becomes agent-visible automatically.
- Writes are never inferred or bulk-registered from OpenAPI.
- Capability/OpenAPI drift fails deployment smoke tests.
- The file may reference only operations already present in the API contract and may not contain SQL, raw query strings, or ad-hoc schema definitions.

### 10.5 Audit behavior

FastMCP writes a `started` audit record before forwarding the operation, then updates it to `succeeded`, `failed`, or `denied`. A request ID is propagated through FastMCP, FastAPI/PostgREST, and logs.

Audit failure must not silently permit a write. For MVP, write tools fail closed if the initial audit record cannot be created.

---

## 11. Object Storage

### 11.1 Bucket model

Use one bucket per project and environment: `{project}-{environment}`.

Backup data must use a separate bucket or, at minimum, separate credentials and a separate prefix that application services cannot access.

### 11.2 Upload flow

1. Authenticated caller requests an upload intent with filename metadata, content type, and expected size.
2. FastAPI authorizes the caller and generates a non-guessable server-controlled key.
3. A `pending` object row is created.
4. FastAPI returns a short-lived presigned PUT URL.
5. Client uploads directly to R2.
6. Client calls the complete endpoint.
7. FastAPI performs an R2 metadata lookup, validates size/type constraints, and marks the row `available`.

Pending uploads older than a configured threshold are eligible for cleanup.

### 11.3 Download flow

- Caller requests a URL by object ID, not arbitrary bucket/key.
- FastAPI verifies ownership or project policy.
- Only `available` objects are downloadable.
- URL TTL is short and configurable.

### 11.4 Storage acceptance tests

- User A cannot obtain a download URL for User B’s object.
- Arbitrary object keys are rejected.
- Oversized or mismatched uploads fail completion.
- A presigned URL is not written to logs or the audit table.
- Abandoned upload intents remain non-downloadable.

---

## 12. Backup and Recovery

### 12.1 Backup model

- pgBackRest repository using an S3-compatible R2 endpoint.
- Continuous WAL archiving.
- Weekly full backup and daily incremental backup.
- Two full backup chains retained.
- Repository encryption enabled with a key stored separately from repository credentials.
- Nightly custom-format `pg_dump` is P2 and may be dropped if PITR is complete and tested.

### 12.2 Trust boundary

Backups in the same Cloudflare account protect against database/node loss but do not provide a fully independent account-compromise disaster-recovery boundary. This limitation must be stated in operations documentation.

Application services must not possess backup-bucket credentials. Backup credentials should not permit access to application object-storage data unless required.

### 12.3 Recovery acceptance

The restore drill must:

1. Create known rows at time T1.
2. Record a recovery marker.
3. Modify/delete rows at T2.
4. Restore into a disposable PostgreSQL volume to a timestamp between T1 and T2.
5. Verify the expected data state.
6. Run application schema and smoke checks against the restored instance.
7. Record measured recovery time and the latest recoverable timestamp.
8. Record the selected backup set, requested recovery target, achieved recovery LSN/timestamp, schema version, and smoke-test outcomes.

A documented command must perform the disposable restore without mounting, overwriting, or mutating the active database volume. The restore evidence is written to a machine-readable JSON file under `evidence/` and retained as part of the release candidate.

---

## 13. Secrets and Bootstrap

### 13.1 Bootstrap boundary

“One-command deployment” means one command **after** DNS and provider/bootstrap credentials are available. The specification must not imply that secret-zero is eliminated.

Required bootstrap inputs may include:

- Cloudflare/R2 provisioning credential.
- Infisical machine identity bootstrap credential.
- DNS/ACME prerequisites.
- VPS SSH access.

`bin/bootstrap-providers.sh` is the only project command permitted to provision, delete, or change external provider resources. Runtime services may communicate only with the pre-provisioned resources they need, using narrowly scoped credentials. `deploy.sh` validates bootstrap outputs and deploys the project; it must terminate before changing the running deployment when any prerequisite is absent and print the complete list of missing items.

### 13.2 Infisical model

The free plan’s identity limit must be respected. The MVP should use a small number of permission-bound machine identities rather than one identity per container:

- Deployment/runtime secrets identity.
- Backup-only identity.
- Optional CI identity.

Secrets are retrieved during controlled deployment or service startup and rendered into Docker secrets, tmpfs, or root-owned restricted runtime files outside the repository. They are not committed, copied into images, printed by deployment scripts, exposed in process arguments, or persisted in a project-local production `.env`. Container restart behavior must include an explicit secret-rematerialization path rather than depending on stale files.

### 13.3 Required secret separation

At minimum, separate:

- JWT private signing key.
- PostgreSQL service credentials.
- Migration credentials.
- R2 application credentials.
- R2 backup credentials.
- pgBackRest repository encryption key.
- Agent credential pepper, if used.

---

## 14. Networking and Edge Security

### 14.1 Public HTTP services

Traefik exposes only:

- HTTPS application/API routes.
- MCP endpoint.
- Authenticated documentation routes.
- Optional public PgBouncer TCP route when explicitly enabled.

HTTP redirects to HTTPS. TLS certificates renew automatically.

### 14.2 Docker discovery

- `exposedByDefault=false`.
- Only explicitly labeled services are routed.
- Traefik receives the minimum Docker API access practical for the deployment, preferably through a restricted socket proxy.
- Database, backup, and secret-rendered files are not mounted into Traefik.

### 14.3 Request controls

Configure:

- Per-IP HTTP rate limits for login, token exchange, admin, storage-presign, and MCP routes.
- Request body size limits.
- Header and idle timeouts.
- MCP response-size and row-count limits.
- Login throttling and temporary credential lockout.
- Security headers appropriate for API/documentation routes.

Rate limiting is a protective control, not an authorization control.

---

## 15. Operations and Diagnostics

### 15.1 Health endpoints

Each service exposes:

- Liveness: process is running.
- Readiness: required dependencies are reachable and migrations are current.

Database readiness checks must not use superuser credentials.

### 15.2 Logging

- Structured logs where supported.
- Request ID propagated across Traefik, FastMCP, FastAPI, PostgREST, and audit records.
- Authorization denials logged without sensitive token contents.
- Presigned URLs, passwords, raw agent secrets, JWTs, and secret values redacted.

### 15.3 `doctor.sh`

The operator command reports:

- Container health.
- TLS route reachability.
- PostgreSQL readiness and version.
- PgBouncer pool state.
- Migration version.
- PostgREST schema-cache/API smoke status.
- Last successful backup and WAL archive status.
- Disk usage and PostgreSQL/WAL volume headroom.
- R2 access checks using least-privilege credentials.

### 15.4 Minimum operational alerts

The MVP does not need a full alerting platform, but it must provide a non-zero exit status or visible failure for:

- Backup failure.
- WAL archiving failure.
- Disk usage above configured threshold.
- Unhealthy database/API/MCP service.
- Certificate renewal or routing failure detected by smoke tests.

---

## 16. Testing and Acceptance Suite

### 16.1 Test harness contract

Pytest is the canonical top-level acceptance-test orchestrator. Fixtures may invoke `psql`, `dbmate`, Prisma, Node, shell commands, HTTP clients, Docker Compose, and restore tooling, but the pass/fail result and release reports are collected through one Pytest entry point.

The harness must support:

- Disposable project/database fixtures.
- Human and agent identity fixtures with explicit scopes.
- Exact-token reuse across revocation tests.
- Subprocess and HTTP assertions with redacted diagnostics.
- Multi-project isolation fixtures.
- Recovery workflow orchestration and evidence validation.
- Parallel execution only where shared state cannot make results flaky.

### 16.2 Security tests

Automate these negative tests:

1. `anon` cannot access protected resources.
2. User A cannot read or mutate User B’s rows.
3. A security-invoker view preserves underlying RLS.
4. No API role can access `app_private` directly.
5. No API role can execute ungranted functions.
6. Newly created functions are not executable by `PUBLIC`.
7. Agent read tokens cannot invoke write tools or write RPCs.
8. Agent write tokens cannot execute arbitrary SQL or unlisted functions.
9. Wrong issuer, audience, algorithm, token type, and expired tokens are rejected.
10. The same access token issued before revocation is rejected immediately by both an MCP read tool and a direct PostgREST request, with documented denial codes; a write attempt is also denied.
11. Tool parameters cannot override `agent_id`, `role`, or scope.
12. SQL injection strings remain data and do not change query structure.
13. Audit records redact secrets and presigned URLs.
14. Storage ownership checks prevent cross-user download.
15. Public routes cannot reach direct PostgreSQL.

### 16.3 Compatibility tests

- `psql` direct connection.
- `psql` pooled connection for supported operations.
- Prisma Migrate through direct URL.
- Prisma Client CRUD through pooled URL.
- Node `pg` client through pooled URL.
- Python PostgreSQL client through pooled URL.
- PostgREST authenticated read/write RPC.
- PostgREST schema-cache reload: an API migration is followed by reload and the changed operation appears in OpenAPI.
- Capability/OpenAPI contract validation and deliberate-drift failure.
- FastAPI auth and storage flow.
- MCP read, write, denial, audit, and revocation flow.

### 16.4 Deployment tests

- Fresh deployment on an empty host/project namespace.
- Re-running `deploy.sh` is safe and converges without destroying data.
- Failed prerequisite validation stops before changing the running deployment.
- Second project deployment uses different Compose project names, networks, volumes, database names, roles, runtime credentials, JWT issuers, JWT audiences, signing keys, routes/hostnames, connection strings, MCP URLs, R2 project buckets or strongly isolated prefixes/credentials, backup stanzas, and backup encryption material.
- Sharing the VPS, Traefik instance, provider account/organization, DNS provider account, or container registry is permitted; sharing project-scoped state or authority is not.
- Removing the second project, revoking its credentials, or restoring its backup does not affect the first.

### 16.5 Lightweight capacity smoke test

No SLA is promised, but record a baseline using a small fixed test:

- Concurrent pooled database clients.
- Concurrent REST reads.
- Concurrent MCP reads with response limits.
- Login/token rate-limit behavior.

The purpose is regression detection and configuration validation, not performance certification.

---

## 17. Twelve-Session Implementation Roadmap

Documentation, tests, and `deploy.sh` evolve in every session; they are not postponed until the end.

**Session completion invariant:** no session is complete until its exit-criteria tests are green and the README/runbook contains the exact commands a new developer will use for that capability.

### Session 1 — Product contract, manifest, repository, and acceptance harness

**Session summary**

Establish the project as a testable product rather than a collection of infrastructure experiments. This session converts the specification into a repository contract: fixed scope tiers, explicit non-goals, a declarative project manifest, pinned dependency versions, standard command entry points, and an executable acceptance harness. The implementation work should remain intentionally shallow; the goal is to make every later session converge on known interfaces and measurable outcomes. By the end of the day, project names, routes, database identifiers, storage prefixes, JWT audiences, and backup names should all be derivable from configuration, while the most important security and compatibility requirements already exist as failing or skipped tests. This creates the reusable skeleton against which all subsequent work is built and prevents deployment assumptions from being scattered across source files.

**Build**

- Freeze P0/P1/P2 scope and non-goals.
- Create repository layout, `project.yaml`, `capabilities.yaml`, `versions.env`, Compose skeleton, and command stubs.
- Freeze the notes/tasks/ownership example domain.
- Write the threat-model matrix and security acceptance checklist.
- Create the Pytest acceptance harness and CI/lint skeleton.
- Pin exact container tags, digests, and resolved versions.
- Make `deploy.sh` render and validate names without deploying services.

**Exit criteria**

- A second example manifest renders collision-free project names and an `outputs.json` schema.
- P0 acceptance tests exist as failing/skipped executable Pytest tests, not prose only.
- No release component uses a floating container tag.

### Session 2 — Host, Traefik, secrets bootstrap, and project isolation

**Session summary**

Create the secure execution environment in which every later service will run. The session provisions and hardens the VPS, installs the container runtime, configures firewall policy, establishes Traefik as the only public ingress, and proves automatic TLS issuance and renewal. It also defines the boundary between provider bootstrap credentials and runtime secrets, integrates the reduced Infisical identity model, and renders secrets without placing them in source control, images, command arguments, or logs. Project isolation must be visible immediately through distinct Compose namespaces, networks, routes, and generated identifiers. The desired outcome is not a complete application stack, but a repeatable and inspectable host foundation where only explicitly labeled services are reachable and where a second project can later coexist without sharing routes, networks, or secret material.

**Build**

- Ubuntu hardening, firewall, Docker, restricted Traefik discovery, ACME.
- Infisical/bootstrap integration using the reduced machine-identity model.
- Enforce the provision-only bootstrap boundary and complete prerequisite reporting.
- Per-project Compose network, route, credential, issuer/audience, and secret-material isolation.
- Secret rendering through Docker secrets/tmpfs or restricted runtime files, without a persistent production `.env`.

**Exit criteria**

- HTTPS health endpoint is reachable.
- Unlabeled containers are not exposed.
- Secret values do not appear in images, repository, Compose output, or logs.

### Session 3 — PostgreSQL, migrations, roles, schemas, and security invariants

**Session summary**

Build the database security model before adding public APIs. This session installs the pinned PostgreSQL and pgvector versions, creates the schema and ownership hierarchy, establishes login and group roles, hardens default privileges, and introduces a deterministic migration runner. A small multi-user example domain should be sufficient to exercise row-level security, security-invoker views, narrow RPC writes, private-schema boundaries, and safe function ownership. The emphasis is on proving negative behavior: users must not cross tenant boundaries, public roles must not reach base or private schemas, and newly created functions must not inherit unsafe execution grants. At the end of the session, PostgreSQL should already embody the main authorization guarantees of the product, independently of FastAPI, PostgREST, or MCP.

**Build**

- PostgreSQL 18 current patch, pgvector, and pinned image/version.
- Four schemas, owner/service/group roles, default-privilege hardening.
- Pinned dbmate migration workflow through `bin/migrate.sh` and its migration table.
- Frozen notes/tasks/ownership example tables with RLS.
- Security-invoker API view and narrow write RPC.

**Exit criteria**

- RLS isolation test passes.
- Base/private schema access tests fail as expected.
- Unsafe default function execution is prevented.

### Session 4 — PgBouncer and standard database developer experience

**Session summary**

Turn the secured PostgreSQL instance into a familiar, framework-compatible database service. The session introduces PgBouncer for transaction-pooled application traffic while retaining a restricted direct connection for migrations and administrative operations that cannot safely use transaction pooling. Connection strings, pool limits, timeouts, and prepared-statement behavior should be generated from the project manifest and tested against the actual clients the primitive promises to support. The critical proof is a split workflow in which Prisma Migrate uses the direct URL and Prisma Client uses the pooled URL, with equivalent smoke tests for Node, Python, and `psql`. This session establishes the most recognizable Neon- or Prisma-like developer experience achievable within the project constraints without exposing the direct database publicly.

**Build**

- Transaction-pooled application endpoint and restricted direct endpoint.
- Connection limits and prepared-statement configuration.
- Generated pooled/direct URLs in the human summary and `outputs.json`.
- `bin/connect.sh` for tunnels, `psql`, Prisma Studio, and environment output.
- Example Node `pg`, Python, and Prisma clients.

**Exit criteria**

- Prisma Migrate works through direct URL.
- Prisma Client works through pooled URL.
- Direct PostgreSQL is not publicly reachable.

### Session 5 — PostgREST, stable API contract, and documentation metadata

**Session summary**

Expose the database through a deliberately narrow and stable HTTP contract. PostgREST is configured to publish only the `api` schema, where reads are represented by RLS-safe views or table-returning functions and writes are represented by explicit RPCs. This session should connect schema design to API behavior by adding SQL comments, row limits, timeouts, schema-cache reload procedures, and an allowlist snapshot of all exposed resources. Authentication may still use temporary development tokens, but the role-switching and claim expectations must match the final token model. The primary result is an independently testable REST surface that preserves PostgreSQL authorization rules, cannot address `app` or `app_private`, and already produces useful OpenAPI documentation through Scalar.

**Build**

- PostgREST exposing only `api`.
- JWT role switching configuration placeholder.
- Row limits, timeouts, schema-cache reload on API DDL.
- SQL comments for OpenAPI.
- Scalar page for PostgREST.

**Exit criteria**

- Exposed resources match an allowlist snapshot.
- A migration-triggered schema-cache reload updates OpenAPI and the contract test observes it.
- `app` and `app_private` cannot be requested.
- RLS works through PostgREST.

### Session 6 — Auth service and asymmetric JWTs

**Session summary**

Replace temporary authentication assumptions with the production-shaped identity flow used by humans, applications, PostgREST, and agents. The FastAPI auth service creates and verifies human credentials, bootstraps project administration, registers agents, issues one-time agent secrets, rotates those secrets, and exchanges valid credentials for short-lived access tokens. JWT signing is asymmetric so only the auth service possesses the private key, while PostgREST and FastMCP receive public verification material. The implementation must derive roles and scopes from server-side records and reject invalid issuer, audience, algorithm, token type, time bounds, or status. This session is complete when credential storage, claim validation, key separation, and secret redaction are demonstrated through automated positive and negative tests rather than only through successful login.

**Build**

- User credential storage and admin bootstrap.
- Human login and `/auth/me`.
- Agent registration, one-time secret, secret rotation, and token exchange.
- Asymmetric JWT signing and public-key verification in PostgREST.
- Issuer, audience, role, scope, token-use, and expiry checks.

**Exit criteria**

- Token-negative test matrix passes.
- Verifying services do not possess the JWT private key.
- Raw user/agent credentials are never stored or logged.

### Session 7 — R2 object-storage vertical slice

**Session summary**

Add the optional but high-value storage capability as one complete, ownership-aware workflow. FastAPI creates a pending upload intent, generates the object key, returns a short-lived presigned PUT URL, verifies the resulting R2 object during completion, and transitions metadata to an available state. Download and deletion operations are addressed by object ID so callers never gain unrestricted bucket or key access. The session should also provide cleanup for abandoned intents and enforce expected size, content type, ownership, and URL expiration constraints. The objective is a narrow vertical slice, not a full storage platform: by the end of the session, one user can upload and retrieve an object while cross-user access, arbitrary keys, incomplete uploads, and sensitive URL logging are reliably prevented.

**Build**

- Upload intent, server-generated key, presigned PUT, completion verification.
- Authorized download URL and deletion/tombstone.
- Object metadata states and cleanup command.

**Exit criteria**

- End-to-end upload/download passes.
- Cross-user access, arbitrary keys, abandoned upload, and logging tests pass.

### Session 8 — FastMCP reads and shared authorization path

**Session summary**

Introduce the agent-facing protocol without creating a second data-access or authorization system. FastMCP validates the caller’s JWT, checks current agent status, filters visible tools by scope, and forwards the original bearer token to protected PostgREST endpoints. The read surface should remain small and structured: resource discovery, resource description, bounded filtering and ordering, and one named report are sufficient to prove the pattern. Every query must use allowlisted resources, columns, and operators, with independent limits on rows, execution time, and response size. The defining acceptance test is equivalence: an agent querying through MCP must receive the same RLS-constrained result it would receive through PostgREST, while never being able to submit raw SQL or an unrestricted REST query string.

**Build**

- Remote MCP endpoint and JWT verification.
- Active-agent middleware.
- `list_resources`, `describe_resource`, `query_resource`, and one named report.
- OpenAPI-assisted wrapper/schema generation constrained by `capabilities.yaml`.
- Frozen resource/column allowlists, structured filters, and response budgets.
- Forward bearer token to PostgREST.

**Exit criteria**

- Tool discovery respects scopes.
- No tool accepts raw SQL or raw PostgREST query strings.
- Adding an API operation does not expose an MCP capability without an explicit capability-file change.
- Deliberate OpenAPI/capability drift fails the smoke test.
- RLS results through MCP match equivalent PostgREST results.

### Session 9 — FastMCP writes, audit, and kill switch

**Session summary**

Complete the agent capability model with explicit writes, durable attribution, and immediate revocation. Two representative project-specific tools should demonstrate the one-tool-to-one-operation pattern, with input validation, required scopes, bounded side effects, and no generic dispatcher. FastMCP records an audit entry before forwarding a request, propagates a request ID through the downstream stack, and completes the record with success, failure, denial, timing, and redacted parameters. PostgREST adds the authoritative active-agent check inside each database request so a previously issued token stops working immediately after revocation. The session succeeds only when unauthorized writes are undiscoverable or denied, all tool outcomes are auditable, audit initialization fails closed for writes, and the same pre-revocation token is rejected on its next read and write attempts.

**Build**

- Two example project-specific write tools.
- Scope-gated tool visibility and execution.
- Started/completed audit lifecycle with redaction and request IDs.
- PostgREST `db-pre-request` active-agent check.
- Admin audit query and revocation endpoint.

**Exit criteria**

- Read-only agent cannot call or discover unauthorized writes.
- Existing token fails on next MCP read and write after revocation.
- Successful, failed, and denied calls appear in audit records.

### Session 10 — Backup, WAL archiving, PITR, and restore drill

**Session summary**

Prove that the primitive can recover data, not merely create backups. The session configures pgBackRest with encrypted R2 storage, retention rules, scheduled full and incremental backups, continuous WAL archiving, and health checks that expose failures. The main deliverable is a disposable, timestamp-targeted restore workflow that never overwrites the active database volume. A controlled T1/T2 data scenario should demonstrate recovery to a point between the two states, followed by migration-version checks and application smoke tests against the restored instance. Recovery time and latest recoverable time must be recorded as evidence. A portable `pg_dump` export is added only if the complete PITR path is already working, because a tested recovery chain is more valuable than multiple unproven backup formats.

**Build**

- pgBackRest R2 repository, encryption, retention, schedules, and checks.
- Continuous WAL archiving.
- Disposable-volume PITR command and runbook.
- Optional portable `pg_dump` only after PITR is proven.

**Exit criteria**

- Timestamp-targeted restore drill succeeds without mounting or mutating the active database volume.
- Restored database passes schema, one RLS-protected read, and one write-RPC smoke test.
- A machine-readable evidence file records the backup set, requested and achieved recovery point, RTO, schema version, and test results.

### Session 11 — Operations, deployment convergence, and complete documentation

**Session summary**

Consolidate the working components into a deployable product experience. `deploy.sh` should progress from a development helper to an idempotent orchestrator that validates prerequisites, renders configuration, starts services, waits for readiness, applies migrations, reloads API metadata, runs smoke tests, and prints usable connection information without exposing secrets. Operational commands should diagnose container health, TLS routing, database and PgBouncer state, migration status, backup and WAL freshness, R2 access, and disk headroom. Documentation is finalized around actual commands and observed behavior, including admin tasks, examples, recovery procedures, and failure handling. A fresh-host rehearsal by following only the README should surface undocumented assumptions before the independent reuse test in the final session.

**Build**

- Mature `deploy.sh`, complete prerequisite reporting, health waits, dbmate migrations, and smoke tests.
- Produce permission-safe `outputs.json` and document `bin/connect.sh`.
- `doctor.sh`, structured logs, request ID propagation, disk/WAL checks, and verbose-mode redaction tests.
- FastAPI Scalar page, documentation index, admin scripts, examples, and runbooks.
- Fresh-host rehearsal.

**Exit criteria**

- A developer follows the README from a clean environment without undocumented commands.
- Re-running deploy is non-destructive and convergent.

### Session 12 — Reuse proof and release candidate

**Session summary**

Validate that the result is genuinely reusable by transferring control to a developer who did not assemble the stack. Using a new manifest and project namespace, that developer should bootstrap and deploy a second project on the same host, exercise database, REST, auth, storage, MCP, auditing, revocation, and restore workflows, and record every place where source edits or undocumented knowledge are required. The full acceptance suite is then run against both projects to prove isolation of routes, networks, volumes, roles, audiences, storage, and backup stanzas. The final activity is evidence-based scope closure: resolve all P0 failures, explicitly list remaining P1/P2 gaps, remove hidden dependencies, and decide whether the artifact is ready as a reusable template or whether future demand justifies a managed control plane.

**Build/test**

- A different developer deploys a second project using a new manifest.
- Run full security, compatibility, deployment, storage, MCP, and restore suites.
- Complete the explicit two-project isolation matrix, distinguishing shared provider accounts from forbidden shared project state.
- Record all manual edits or project-specific assumptions.
- Remove or document every hidden dependency.
- Decide whether the result is a reusable template or warrants a future control plane.

**Exit criteria**

- Both projects operate independently on the same host.
- No source-file edits were required for project names, routes, roles, buckets, audiences, or backup stanzas.
- All P0 tests pass.
- Remaining P1/P2 gaps are explicitly listed with evidence and estimated effort.

---

## 18. Final Release Gate

The MVP is complete only when all of the following are true:

- [ ] Exact container image tags, digests, and resolved versions are locked.
- [ ] Standard pooled and direct database URLs work with documented clients and `bin/connect.sh`.
- [ ] Prisma migration/client compatibility is demonstrated.
- [ ] Only the `api` schema is exposed through PostgREST.
- [ ] RLS isolation and security-invoker behavior are tested.
- [ ] JWT validation is asymmetric and includes issuer/audience checks.
- [ ] Agent credentials are hashed and shown only once.
- [ ] `capabilities.yaml` is validated against live OpenAPI, and API additions are not implicitly exposed to agents.
- [ ] No agent-facing capability accepts arbitrary SQL.
- [ ] Every agent tool attempt is auditable with redaction.
- [ ] A revoked agent’s existing token is rejected on its next request.
- [ ] Object upload/download ownership checks pass.
- [ ] WAL archiving and a timestamp-targeted disposable restore pass without touching the active volume.
- [ ] Restore evidence records the selected backup, requested/achieved recovery point, RTO, schema version, and smoke results.
- [ ] Deployment emits permission-safe `outputs.json` and is repeatable and non-destructive on re-run.
- [ ] A second isolated project passes the explicit project-state and authority isolation matrix without source edits.
- [ ] The full acceptance suite is orchestrated through Pytest.
- [ ] Every completed session has green exit tests and documented operator commands.
- [ ] A new developer can complete the documented happy path.

---

## 19. Post-MVP Candidates

Only after the release gate:

1. Human refresh-token rotation and browser-oriented auth.
2. Public pooled database endpoint automation and customer-specific network controls.
3. Generated SDKs and a small project CLI.
4. Managed embedding provider and ingestion pipeline.
5. Read replicas.
6. Ephemeral test databases using full-copy or snapshot techniques.
7. Query cache/edge proxy.
8. Central control plane for multiple hosted projects.
9. Independent backup account/provider.
10. OpenTelemetry metrics/traces and alert integrations.
