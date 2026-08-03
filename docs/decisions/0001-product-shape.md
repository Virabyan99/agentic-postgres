# 0001 — Product shape is a one-project-per-deployment appliance

- **Status:** Accepted
- **Date:** 2026-08-03
- **Session:** 1
- **Affects:** `DEP-001`, `DEP-002`, `DEP-ISO-001`

## Context

There are two coherent shapes for a project like this, and they diverge
almost immediately in the data model.

A **shared control plane** hosts many projects on common infrastructure and
separates them logically — by schema, by row-level policy, by tenant column.
Isolation is then a property of the application's correctness, and every
future feature has to re-establish it.

An **appliance** deploys one project per instance. Isolation is a property of
the deployment topology, and the application cannot violate it by being
wrong.

The choice must be made before any identifier is derived, because it decides
whether project scope is a runtime value or a deployment-time constant.

## Decision

The product is a reusable, isolated, **one-project-per-deployment** Postgres
appliance and template. It is not a shared managed control plane.

Every project-scoped identity — database name, role names, network names,
volume names, Compose project name, JWT issuer and audience, secret
namespace, storage prefix, backup stanza — is derived deterministically from
one non-secret manifest at render time, and is distinct across projects.

## Consequences

Makes easy:

- Isolation is provable by comparing two rendered manifests, which is what
  runbook §8 does. It does not require a running system.
- A project can be destroyed by removing its deployment, with no risk of
  deleting a neighbour's rows.
- Blast radius of a credential compromise is one project.

Makes hard:

- Per-project overhead is real. Ten projects means ten Postgres instances.
  This is the cost being deliberately accepted.
- Cross-project reporting has no supported path and is out of scope.

Forecloses:

- Any future feature that assumes a shared catalog, a global user table, or a
  tenant discriminator column.

Enforced by `tests/contract/test_render_isolation.py`, which compares parsed
semantic fields across the two fixtures rather than searching for duplicate
strings.

## Alternatives considered

**Shared control plane with RLS-based tenancy.** Rejected: it makes isolation
a correctness property of every future query, and Session 1 would be unable
to prove isolation at all without a running database.

**Shared Postgres instance, one database per project.** Rejected as a middle
ground that inherits the worst of both: a shared failure domain and a shared
superuser, while still paying most of the per-project overhead.
