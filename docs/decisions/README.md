# Architecture Decision Records

An ADR records a decision that is expensive to reverse, together with the
context that made it the right call. It is not a design document and not a
status report.

## When an ADR is required

- Changing anything frozen in runbook §4 (product shape, requirement ID
  prefixes, the example domain, configuration authority, the generated
  endpoint rule, the acceptance-test lifecycle, the evidence lifecycle).
- Removing or weakening a P0 requirement.
- Changing the deterministic naming algorithm, the generated output schema,
  or the version-lock format.
- Resolving an ambiguity that is not already closed in
  `docs/plans/session-01-implementation-plan.md` §2.

That last rule is the important one. An ambiguity discovered during
implementation does not get settled inline in whichever file happened to
surface it. It comes back here.

## Numbering

Sequential, zero-padded to four digits, never reused. A superseded ADR keeps
its number and gains a `Superseded by` line; it is not deleted, because the
reasoning that led to the original choice is usually the reason the
replacement is correct.

## Template

```markdown
# NNNN — Short imperative title

- **Status:** Proposed | Accepted | Superseded by [NNNN](NNNN-slug.md)
- **Date:** YYYY-MM-DD
- **Session:** N
- **Affects:** requirement IDs, or "none"

## Context

What forced a decision. Include the constraint that made the obvious option
wrong, if there was one.

## Decision

The commitment, stated so that a reader can tell whether a given piece of
code complies with it.

## Consequences

What this makes easy, what it makes hard, and what it forecloses. Name the
tests that enforce it.

## Alternatives considered

Each with the reason it was not chosen. "We didn't think of it" is a valid
entry when discovered later.
```

## Index

Every file matching `NNNN-*.md` in this directory must appear below. An
unlisted ADR is one nobody reads, and `0004` went unlisted for a session.

| ADR | Title | Session | Status |
|---|---|---|---|
| [0001](0001-product-shape.md) | Product shape is a one-project-per-deployment appliance | 1 | Accepted |
| [0002](0002-configuration-authority.md) | Configuration authority and transactional rendering | 1 | Accepted |
| [0003](0003-example-domain.md) | Frozen example domain | 1 | Accepted |
| [0004](0004-version-lock-format.md) | Version lock format and offline verification | 1 | Accepted |
| [0005](0005-route-reservation.md) | Reserved routes and segment-wise overlap | 1 | Accepted |
| [0006](0006-capability-scopes.md) | Approved scope vocabulary lives in the capability schema | 1 | Accepted |
| [0007](0007-bounds-authority.md) | The project schema is the sole authority for numeric bounds | 1 | Accepted |
| [0008](0008-sensitive-key-policy.md) | Sensitive key detection by terminal token, never substring | 1 | Accepted |
| [0009](0009-host-and-edge-plane.md) | Host configuration is separate, and one edge plane is shared | 2 | Accepted |
| [0010](0010-secret-materialization.md) | Secrets are individual files in immutable generations | 2 | Accepted |
| [0011](0011-provider-bootstrap-state.md) | Provider ownership is recorded by ID, and convergence is keyed narrowly | 2 | Accepted |
| [0012](0012-output-document-kinds.md) | Two output document kinds under one versioned schema | 2 | Accepted |
| [0013](0013-compose-wrapper-scopes.md) | Compose wrapper scopes, the runtime gate, and three env files | 2 | Accepted |
| [0014](0014-gate-scope-and-session-derivation.md) | The Session 1 gate measures Session 1's claims, at the session the tree targets | 2 | Accepted |
| [0015](0015-reserved-health-route.md) | The platform health route is reserved | 2 | Accepted |
| [0016](0016-absence-is-not-a-collision.md) | Two projects that both lack a facility do not collide | 2 | Accepted |
| [0017](0017-stub-lifecycle.md) | A stub that becomes real stops returning 10 | 2 | Accepted |
| [0018](0018-daemon-access-is-not-a-verdict.md) | A check that cannot reach the daemon reports that, not a verdict | 2 | Accepted |
| [0019](0019-query-strings-cannot-be-dropped.md) | Traefik cannot drop query strings, so the path goes instead | 2 | Accepted |
