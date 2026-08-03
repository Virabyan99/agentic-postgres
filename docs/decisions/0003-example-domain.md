# 0003 — Frozen example domain

- **Status:** Accepted
- **Date:** 2026-08-03
- **Session:** 1
- **Affects:** `SEC-RLS-001`, `SEC-VIEW-001`, `AGT-READ-001`, `AGT-WRITE-001`, `STO-OWN-001`

## Context

The example domain is not a demo. It is the fixture that every security
proof in this project runs against. `SEC-RLS-001` ("user A cannot access user
B's rows") is meaningless without concrete rows, concrete owners, and a
concrete definition of what "access" means.

If the domain is allowed to drift — a column added here, a status value
renamed there — every test that depends on it drifts with it, and the
security guarantees quietly stop meaning what they meant when they were
written.

## Decision

The P0 example domain is frozen as:

- **`notes`** — owner-scoped `title` and `content`.
- **`tasks`** — owner-scoped `title`, `description`, and a bounded `status`.
- **Human-user ownership on every row.** There is no unowned row and no
  system-owned row. Ownership is not nullable.
- **Optional object attachment**, added only after object storage exists
  (Session 7). Not present before then.

Task status values are frozen as exactly:

```text
pending | in_progress | completed | cancelled
```

The minimum later API operations are:

1. Read notes visible to the caller.
2. Create one note owned by the caller.
3. Read tasks visible to the caller.
4. Change one task's status through a narrow operation.

Operation 4 is deliberately not "update a task". A narrow status transition
is expressible as a single PostgREST RPC with an approved shape, which is
what `capabilities.yaml` can safely reference; a general update is not.

Session 3 owns the SQL implementation. Session 1 owns only this contract.

## Consequences

Makes easy:

- Every ownership test has an unambiguous subject. "User A cannot read user
  B's notes" is directly executable.
- The capability catalog in `docs/capability-plan.md` maps 1:1 onto this
  domain, so an agent capability cannot reach data the domain does not model.
- `AGT-WRITE-001` ("a read-only agent cannot discover or invoke writes") has
  a finite write surface to enumerate: two RPCs.

Makes hard:

- Adding a domain concept later requires an ADR superseding this one, plus
  matching updates to the capability plan and the affected acceptance tests.
- Nothing may depend on a nullable owner, including future admin tooling.

## Alternatives considered

**A richer domain (projects, labels, comments, assignments).** Rejected: it
multiplies the number of ownership paths that must be independently proven
without strengthening any single guarantee. The interesting security property
is cross-user denial, and two tables demonstrate it as completely as six.

**Leaving `status` open as free text.** Rejected: a bounded enum is what makes
"change one task's status through a narrow operation" a safe capability. Free
text would force the write path to accept an arbitrary string.

**Allowing system-owned rows** for seed or demo data. Rejected: it introduces
a row that no RLS policy naturally covers, which is exactly the shape of the
bug `SEC-RLS-001` exists to catch.
