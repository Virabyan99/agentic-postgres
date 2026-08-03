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

| ADR | Title | Status |
|---|---|---|
| [0001](0001-product-shape.md) | Product shape is a one-project-per-deployment appliance | Accepted |
| [0002](0002-configuration-authority.md) | Configuration authority and transactional rendering | Accepted |
| [0003](0003-example-domain.md) | Frozen example domain | Accepted |
