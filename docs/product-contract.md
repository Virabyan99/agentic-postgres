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
<!-- Populated in Run 5 from tests/acceptance-registry.yaml by
     bin/render-acceptance-matrix.py --requirements --write.
     Do not hand-edit. -->
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
| `database.max_client_connections` | 1 | 10,000 | PgBouncer client connection ceiling. |
| `database.pool_size` | 1 | 1,000 | Server-side pool size. Must not exceed max_client_connections. |
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
