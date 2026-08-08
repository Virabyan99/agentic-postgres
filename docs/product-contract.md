# Product contract

This document freezes what the product is, what it is not, and which
guarantees are release-blocking. It is the reference every later session is
measured against.

Two of its sections are **generated** and must not be hand-edited. See
"Generated sections" at the end for why, and for how to regenerate them.

---

## 1. Product definition

A reusable, isolated, one-project-per-deployment PostgreSQL appliance and
template. One deployment serves exactly one project. Project isolation is a
property of the deployment topology, not of application correctness.

A deployment provides, when complete:

- A PostgreSQL database with row-level ownership enforced in the database.
- Pooled and direct connection endpoints, each with a documented use.
- A REST surface (PostgREST) and an application API (FastAPI) behind a single
  edge router.
- A narrow, explicitly enumerated agent capability surface (MCP) that is a
  strict subset of the API surface.
- Object storage scoped to the project.
- Point-in-time backup and a rehearsed, verified restore path.

See [0001 — Product shape](decisions/0001-product-shape.md).

## 2. The intended boundary — "low-effort wins toward Neon / Prisma Postgres"

This project is not attempting to be Neon or Prisma Postgres. It is
attempting to capture the parts of their developer experience that are cheap
to reproduce on a single owned host, and to be explicit about the parts that
are not.

**In the boundary — worth reproducing:**

- One command renders a complete, valid project configuration from a single
  non-secret manifest.
- Pooled and direct connection strings that work with unmodified Prisma,
  `psql`, and standard drivers, with the pooled/direct distinction made
  explicit rather than discovered through a migration failure.
- Migrations that run against the direct endpoint without special
  configuration.
- Deterministic, collision-free project identities, so a second project on
  the same host cannot reach the first.
- A restore that is rehearsed rather than assumed.

**Outside the boundary — deliberately not reproduced:**

- Autoscaling, scale-to-zero, and compute/storage separation.
- Instant branching and copy-on-write database forks.
- A hosted control plane, web console, or multi-region availability.
- Managed failover. Recovery here is restore-based and has a real RTO.

The honest summary: this gives a small team most of the *ergonomics* of a
managed Postgres on infrastructure they control, and none of the *elasticity*.

## 3. Requirement catalog

Requirement IDs are stable and are used identically in this document, in
`tests/acceptance-registry.yaml`, in `docs/threat-model.md`, in test markers,
and in the roadmap.

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

Priorities:

- **P0** — release-blocking. May not exist only as prose; each has at least
  one collectible Pytest node ID.
- **P1** — important, not release-blocking. Deferral requires evidence.
- **P2** — optional capability.

<!-- BEGIN GENERATED: requirements -->
<!-- Generated from tests/acceptance-registry.yaml by
     bin/render-acceptance-matrix.py --write. Do not hand-edit. -->

**P0 — 84 requirements**

| ID | Session | Guarantee |
|---|---:|---|
| `CFG-001` | 1 | A project manifest validates against schema and semantics, and contains no secret material. |
| `CFG-002` | 1 | Ambiguous YAML is rejected outright rather than resolved silently. Default PyYAML keeps the last value for a duplicate key. |
| `CFG-003` | 1 | Every identity is derived deterministically and per-context, and no PostgreSQL role can exceed 63 bytes regardless of input length. |
| `CFG-004` | 1 | Identical inputs render byte-identical output, in the same process and across processes, with no timestamp anywhere in the document. |
| `CFG-005` | 1 | Generated output conforms to its schema, records real input digests, and represents nonexistent endpoints as unavailable rather than as placeholders. |
| `CFG-006` | 1 | Every generated file is mode 0600, independent of the process umask. |
| `CFG-007` | 1 | A render that fails validation or publication leaves the previous valid render byte-identical and removes its staging directory. |
| `CFG-008` | 1 | The renderer refuses symlinked inputs and output targets. |
| `CFG-009` | 1 | Secret-bearing keys are rejected in manifests and in output, without false positives for safe reference names such as password_secret_ref. |
| `CFG-010` | 1 | Public pooler exposure requires a specific CIDR allowlist; a default route is not an allowlist. |
| `CFG-011` | 1 | Route trees may not collide with a reserved route or with each other, and overlap is decided segment-wise rather than by string prefix. |
| `CFG-012` | 1 | Two similar projects render fully disjoint identities, compared over parsed semantic fields rather than by duplicate-string search. |
| `CFG-013` | 1 | The capability surface is empty by default, cannot be enabled without a live backing contract, and cannot express SQL or a raw query. |
| `CFG-014` | 1 | Container images are pinned to immutable digests for one declared platform, Python dependencies are hash-locked, and drift is detected offline. |
| `CFG-015` | 1 | The Compose model renders the exact resource names published in outputs.json, cannot be overridden by inherited environment variables, and refuses to start a container in Session 1. |
| `DX-002` | 1 | Operator commands document themselves, obey the exit-code convention, work from any directory, and never print the environment. |
| `DX-003` | 1 | The repository has its required shape, generated output stays out of Git, and no deployable source file hard-codes a fixture identity. |
| `CFG-016` | 2 | The deployed document is a distinct owner-only document kind that records observed host state, cannot be produced by migrating a rendered one, and is never accepted where a rendered document is required. |
| `DEP-ISO-002` | 2 | Two projects sharing one host and one edge share no route, network, or ingress attachment, and stopping one leaves the other served. |
| `DEP-PROV-001` | 2 | Provider ownership is recorded by identifier rather than by name, and re-applying the bootstrap converges without creating a second identity. |
| `DEP-REL-001` | 2 | What systemd runs is an immutable root-owned release identified by commit, never a checkout, so switching a branch cannot change what starts next boot. |
| `OPS-HEALTH-001` | 2 | Every deployed project answers the reserved health route with its own project key, through the edge only, and no unrouted path is served. |
| `SEC-DOCKER-001` | 2 | The publicly reachable proxy reads the Docker API through an allowlisting socket proxy that refuses every write, and the daemon itself is reachable over no network socket. |
| `SEC-HOST-001` | 2 | The host admits key-based SSH only, refuses root and password logins as OpenSSH actually resolves them, patches itself without rebooting itself, and exposes no public listener beyond SSH and the edge. |
| `SEC-LOG-001` | 2 | No request query-string value and no request header value reaches the edge access log, proved by sending a value nothing else could produce and then looking for it in a log known to be recording the request. |
| `SEC-NET-001` | 2 | No public route reaches the direct PostgreSQL endpoint: nothing listens on it, no forwarded path carries it, and a full-TCP connect scan from another network finds it closed while 443 is open. |
| `SEC-NET-002` | 2 | Only the edge publishes a host port, and forwarded public traffic to anything else is dropped by a DOCKER-USER policy that matches the pre-DNAT destination port rather than the container's. |
| `SEC-SECRET-001` | 2 | Secret values appear in no image, repository file, Compose output, log, or evidence file, proved by searching for a real value rather than by asserting that none was written. |
| `SEC-SECRET-002` | 2 | A materialized secret is a mode 0400 file owned by its declared consumer, mounted into that service and no other, proved by the mount list rather than by comparing digests of what each service read. |
| `SEC-TLS-001` | 2 | The public origin serves TLS 1.2 or better with a certificate a default trust store accepts, permanently redirects plaintext, and serves the exact certificate the deployed document records. |
| `DBX-MIG-001` | 3 | Bootstrap authority and migration authority are distinct and least privileged. Proved from the membership option columns, not from the role's own INHERIT attribute. See ADR 0026. |
| `DBX-MIG-002` | 3 | Rendering a migration twice from one input produces identical bytes, and those bytes agree with the committed released lock. See ADR 0028. |
| `DBX-MIG-003` | 3 | An applied migration cannot be silently edited, removed, or reordered; the preflight refuses on any disagreement between its five sources. |
| `DBX-PG-001` | 3 | The locked PostgreSQL 18 image runs with pgvector present at the locked version, in the extensions schema rather than in public. |
| `DBX-PG-002` | 3 | PostgreSQL publishes no host port, joins no edge network, and carries no Traefik label. It is reachable only on its own project network. |
| `DBX-PG-003` | 3 | An existing data volume is bound to one project identity, and a mismatch is refused with exit 11 rather than adopted. See ADR 0030. |
| `DEP-BOOT-001` | 3 | A project restarted by systemd, or restored after a reboot, comes back from the release its deployed document records, through the session that document records, with its cluster identity and applied migrations intact. |
| `DEP-ISO-003` | 3 | Two deployed projects have isolated clusters, volumes, roles, credentials and identity sentinels, and neither project's credential authenticates against the other. |
| `SEC-DB-001` | 3 | No runtime role holds SUPERUSER, CREATEDB, CREATEROLE, REPLICATION or BYPASSRLS. Read from the catalog, never inferred from how a role was created. |
| `SEC-DB-002` | 3 | The public, app and app_private schema boundaries match the contract, and the API roles cannot address the private schemas at all. |
| `SEC-DEFAULT-001` | 3 | Default EXECUTE on newly created functions is revoked from PUBLIC. |
| `SEC-FUNC-001` | 3 | An API role cannot execute a function it was not explicitly granted. |
| `SEC-OWNER-001` | 3 | Objects are owned by a non-login role that no service connects as. |
| `SEC-RLS-001` | 3 | A user can neither read nor mutate another user's rows. |
| `SEC-VIEW-001` | 3 | A security-invoker view preserves the underlying row policy. |
| `DBX-001` | 4 | Prisma Migrate runs through the direct endpoint. |
| `DBX-002` | 4 | Prisma Client operates through the pooled endpoint. |
| `DBX-003` | 4 | psql connects through both the direct and pooled endpoints. |
| `DBX-005` | 4 | The direct endpoint is not publicly reachable. |
| `API-CACHE-001` | 5 | An API migration reloads the schema cache and updates OpenAPI. |
| `API-LIMIT-001` | 5 | Row limits and timeouts are enforced by the server, not the client. |
| `API-SCHEMA-001` | 5 | Only the api schema is exposed, matching a committed allowlist. |
| `SEC-ANON-001` | 5 | The anonymous role cannot reach protected resources. |
| `SEC-PRIV-001` | 5 | No API role can address the app or app_private schemas. |
| `API-ADMIN-001` | 6 | Admin endpoints require an explicit admin scope, not a role name. |
| `API-AUTH-001` | 6 | Login issues a short-lived token and the identity endpoint reflects it. |
| `SEC-CRED-001` | 6 | Raw user and agent credentials are never stored or logged. |
| `SEC-JWT-001` | 6 | Wrong issuer, audience, algorithm, token type, or expiry is rejected. |
| `SEC-KEY-001` | 6 | Verifying services hold public material only. |
| `STO-KEY-001` | 7 | Object keys are generated server-side; client keys are rejected. |
| `STO-OWN-001` | 7 | A user cannot obtain a download URL for another user's object. |
| `STO-URL-001` | 7 | A presigned URL never reaches a log or the audit table. |
| `AGT-BUDGET-001` | 8 | Row and response-size budgets are enforced server-side. |
| `AGT-DRIFT-001` | 8 | Adding an API operation does not expose an agent capability without an explicit capabilities.yaml change. |
| `AGT-READ-001` | 8 | An agent read through MCP equals the equivalent PostgREST result. |
| `AGT-SCOPE-001` | 8 | Tool discovery is filtered by the caller's scopes. |
| `AGT-SQL-001` | 8 | No agent input accepts SQL, a SQL fragment, or a raw query string. |
| `SEC-INJ-001` | 8 | An injection payload stays data and does not alter query structure. |
| `AGT-AUDIT-001` | 9 | Read, write, denied, and failed attempts are audited with redaction. |
| `AGT-AUDITFAIL-001` | 9 | A write fails closed when its audit record cannot be created. |
| `AGT-WRITE-001` | 9 | A read-only agent can neither discover nor invoke a write. |
| `SEC-PARAM-001` | 9 | Tool parameters cannot override agent identity, role, or scope. |
| `SEC-REV-001` | 9 | A token issued before revocation is denied on its next read and write through both MCP and PostgREST. |
| `REC-EVID-001` | 10 | Restore evidence records backup set, requested and achieved recovery point, RTO, schema version, and test outcomes. |
| `REC-PITR-001` | 10 | A timestamp-targeted restore into a disposable volume succeeds. |
| `REC-SAFE-001` | 10 | The restore path never mounts, overwrites, or mutates the active volume. |
| `REC-SMOKE-001` | 10 | The restored instance passes schema, RLS read, and write-RPC checks. |
| `DEP-001` | 11 | A fresh project deploys on an empty host from documentation alone. |
| `DEP-002` | 11 | Re-running deployment converges without destroying data. |
| `DEP-PRE-001` | 11 | A missing prerequisite stops deployment before it changes anything, and lists every absent item. |
| `OPS-001` | 11 | The diagnostic command reports every required check without secrets. |
| `DEP-ISO-001` | 12 | Two projects on one host share no state or authority; shared provider accounts are permitted, shared project scope is not. |
| `DEP-REMOVE-001` | 12 | Removing one project does not affect another. |
| `DX-001` | 12 | A developer who did not build the primitive completes the documented path without source edits or undocumented commands. |

**P1 — 4 requirements**

| ID | Session | Guarantee |
|---|---:|---|
| `DBX-004` | 4 | Node and Python drivers round-trip a query through the pooler. |
| `STO-COMPLETE-001` | 7 | Only objects verified against storage become downloadable. |
| `REC-WAL-001` | 10 | A WAL archiving failure produces a visible non-zero signal. |
| `OPS-LOG-001` | 11 | One request ID propagates across ingress, API, agent, and audit records. |

Full node IDs are in [the acceptance matrix](acceptance-matrix.md).

<!-- END GENERATED: requirements -->

## 4. Numeric bounds

Bounds are declared once, in `schemas/project.schema.json`, because that is
the only copy that is machine-consumed at validation time. The table below is
generated from it. Cross-field *relations* cannot be expressed in JSON Schema
and live in `src/agentic_postgres/config.py`; they are listed separately.

<!-- BEGIN GENERATED: bounds -->
<!-- Generated from schemas/project.schema.json by
     bin/render-config.py --bounds-doc --write. Do not hand-edit. -->

| Field | Minimum | Maximum | Meaning |
|---|---:|---:|---|
| `api.max_rows` | 1 | 10,000 | Global PostgREST row-return ceiling. |
| `backup.retain_full` | 1 | 12 | Full backup chains retained. |
| `database.maintenance_work_mem_mb` | 16 | 512 | VACUUM and index-build working memory. Charged in full against the guardrail because one maintenance operation can hold it for a long time. |
| `database.max_client_connections` | 1 | 10,000 | PgBouncer client connection ceiling. |
| `database.max_connections` | 10 | 200 | PostgreSQL max_connections on the cluster itself, not the pooler's ceiling. Deliberately small: Session 4's answer to connection count is a pooler, and a large per-cluster limit would make the pooler decorative. |
| `database.memory_limit_mb` | 128 | 4,096 | The container mem_limit. NOT the same number as the guardrail: a container limit caps page cache too, so a limit set equal to the unreclaimable budget makes the cluster live in permanent cache reclaim. Measured at 512 MiB with these defaults, two clusters pegged their limit with several hundred reclaim events and no OOM kill. Must exceed the derived unreclaimable budget. |
| `database.pool_size` | 1 | 1,000 | Server-side pool size. Must not exceed max_client_connections. |
| `database.shared_buffers_mb` | 16 | 1,024 | PostgreSQL shared_buffers. Counts in full against the memory guardrail: it is shared memory, which no swap can relieve and no cache reclaim can shrink. |
| `database.shm_size_mb` | 64 | 1,024 | The container /dev/shm size. PostgreSQL's dynamic shared memory for parallel query lands here, and Docker's 64 MiB default is below the default shared_buffers. Must be at least shared_buffers_mb. |
| `database.work_mem_mb` | 1 | 64 | Per-sort-node working memory. Allocated on demand, so it does not multiply by max_connections in practice; the guardrail charges a flat per-backend anonymous allowance instead. See the Session 3 plan 3.3. |
| `mcp.max_response_bytes` | 1,024 | 10,485,760 | Agent response size ceiling. |
| `mcp.max_result_rows` | 1 | 1,000 | Agent read row ceiling. Must not exceed api.max_rows. |
| `storage.download_url_ttl_seconds` | 60 | 3,600 | Presigned download URL lifetime. |
| `storage.max_upload_bytes` | 1 | 5,368,709,120 | Largest accepted upload. P0 default is 25 MiB. |
| `storage.upload_url_ttl_seconds` | 60 | 3,600 | Presigned upload URL lifetime. |

Relations between these fields cannot be expressed in JSON Schema and are
enforced in `src/agentic_postgres/config.py`:

- `database.pool_size` must not exceed `database.max_client_connections`
- `mcp.max_result_rows` must not exceed `api.max_rows`
- `api.public_base_path` and `mcp.public_base_path` must not overlap segment-wise
- Neither base path may overlap a reserved route
- `database.pooled_public_cidrs` must be non-empty when `database.pooled_public` is true, and may not contain a default route
- `database.shm_size_mb` must be at least `database.shared_buffers_mb`
- `database.memory_limit_mb` must exceed the derived unreclaimable budget
- The derived unreclaimable budget must not exceed the per-project memory guardrail

<!-- END GENERATED: bounds -->

## 5. Non-goals

These are not deferred. They are outside the product.

- A shared, multi-tenant control plane, or any cross-project shared catalog.
- A hosted web console or SaaS offering.
- Autoscaling, scale-to-zero, or compute/storage separation.
- Database branching or copy-on-write forks.
- Automatic failover or multi-region replication.
- Arbitrary SQL execution by an agent, under any authentication.
- General-purpose ORM support beyond the endpoint contract in `DBX`.
- Cross-project reporting or aggregation.

The agent constraint is the load-bearing one. An agent's reachable surface is
exactly the set of capabilities enumerated in `capabilities.yaml`, each bound
to one pre-existing operation with an approved shape. There is no path by
which an agent submits a query, a fragment, a column list, or a path.

## 6. Session 12 success criterion

Session 12 succeeds when, on a host that has never run this software:

1. A new team member follows `docs/new-team-member.md` end to end without
   editing source code.
2. Two projects deploy to the same host and neither can reach the other's
   data, roles, secrets, storage objects, or backups — proven by
   `DEP-ISO-001`, not asserted.
3. Every P0 requirement has at least one **active** test. None remains
   `future`.
4. A point-in-time restore to a specified timestamp is performed against a
   disposable target and the restored data is verified by query.
5. An agent with a read-only capability set cannot discover or invoke any
   write, and every attempt — allowed, denied, or failed — is audited with
   redaction.
6. `bin/session-12-check.sh` exits `0` from a clean tracked tree.

## 7. Change control

**Removing or weakening a P0 requirement** requires explicit approval and an
ADR recording what guarantee is being given up and who accepted the risk.
Deleting the test is not weakening the requirement — it is hiding it, and the
registry check fails on a P0 row with no node ID.

**Adding P0 scope** requires, in the same change: a requirement ID, an owning
session, a registry entry, and at least one collectible node ID. A P0
requirement may enter as a `future` placeholder, but the placeholder body must
fail if executed. A requirement with no test is not P0.

**Deferring P1 or P2** requires documented evidence of why, and a target
session. "Not yet" without a session is not a deferral.

**Any ambiguity discovered during implementation** is resolved in
`docs/plans/session-01-implementation-plan.md` §2 or in a new ADR — never
inline in the file that happened to surface it.

## Generated sections

Sections 3 and 4 are generated. The reason is drift: a P0 requirement listed
here but absent from `tests/acceptance-registry.yaml` is a guarantee nobody
tests, and hand-maintaining both copies guarantees that eventually happens.
Generating this table from the registry makes the failure structurally
impossible rather than merely detectable.

Regenerate:

```bash
python bin/render-config.py --bounds-doc --write        # section 4  (Run 2)
python bin/render-acceptance-matrix.py --requirements --write   # section 3  (Run 5)
```

Both have `--check` modes, run by CI and by `bin/session-01-check.sh`, which
fail on drift and never write.
