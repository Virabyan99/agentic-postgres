# 0027 — The output schema gains a version, and a migration path with it

- **Status:** Accepted
- **Date:** 2026-08-07
- **Session:** 3
- **Affects:** CFG-016, DEP-ISO-003

## Context

Session 3 adds database facts to `outputs.json`: the observed server version,
the observed extension set, the container and volume identities, and the
per-project memory budget. `schemas/outputs.schema.json` currently pins
`schema_version` to `enum: [2]` on both document branches, and `$defs.database`
is `additionalProperties: false`. So the fields cannot be added without a schema
change either way — the only question is whether the version number moves with
them.

Leaving it at `2` is tempting because nothing in the repository reads
`schema_version` to decide behaviour today. That is exactly why it would be
wrong. `schema_version` is not for this repository at this commit; it is for a
reader that encounters a document it was not written for. A v2 reader handed a
document with `database.observed` in it should reject the document, not skip the
key it does not recognise and report success on a partial understanding.

The version number is the cheap part. What makes it mean anything is
`src/agentic_postgres/output_migrations.py` and the committed
`tests/fixtures/outputs-v1.json`: there is already a real migration path with a
real fixture, and a bump that did not extend it would leave the path claiming to
handle every version while handling one.

## Decision

`schema_version` becomes `3` on both document branches — rendered and deployed.

Paid for in full, in the same run:

- `schemas/outputs.schema.json` gains the Session 3 fields under `$defs.database`
  on both branches, and `additionalProperties: false` stays;
- `output_migrations.py` gains a `v2 → v3` function;
- `tests/fixtures/outputs-v2.json` is committed, alongside the existing
  `outputs-v1.json`, so the v1 → v2 → v3 chain is exercised end to end rather
  than only its newest link;
- the standing rule holds: **migration never produces a deployed document.** A
  migrated document is a rendered document. Anything that was observed on a host
  was observed under the schema in force at the time, and inventing observations
  during a version migration would be the purest form of this project's
  recurring defect.

`database.direct` and `database.pooled` stay `unavailable` with
`available_from_session: 4` (D41). The version bump is not an occasion to
publish an endpoint Session 3 does not offer.

## Consequences

Every future session that adds an output field now has a worked example of what
that costs, and the cost is deliberately not zero.

`test_the_deployed_document_still_reports_no_direct_endpoint` keeps passing
unchanged, because the endpoint branches are untouched. That test is a P0 proof
of `SEC-NET-001` and it belongs to `DBX-005` in Session 4; if a Session 3 change
had made it fail, the change would have been wrong.

What this makes harder: a reader pinned to v2 stops working against freshly
rendered documents the moment this lands. That is the intended behaviour, and it
is why the migration path exists rather than a tolerant parser.

Enforced by:

- `tests/contract/test_output_migrations.py` (extended, Run 2)
- `tests/contract/test_output_schema.py` over both branches (Run 2)
- `CFG-016` — the generated output document validates against its schema

## Alternatives considered

**Add the fields without bumping the version.** Nothing in the tree would
notice. Every reader outside the tree would silently downgrade to a partial
understanding of a document it believes it fully understands, and there would be
no version at which the new fields became guaranteed.

**Bump to 3 and skip the `v2 → v3` migration** on the grounds that no v2
document exists in the wild. Deployed documents on the host are v2 right now, so
this is false. It would also leave `output_migrations.py` asserting a capability
it no longer has.

**Set `additionalProperties: true` on `$defs.database`** so future sessions can
add fields freely. Turns the schema from a contract into a suggestion, and the
first typo in a field name becomes an accepted document rather than a rejected
one.

**Carry a separate `database_schema_version`.** Two version numbers over one
document, disagreeing eventually. The document has one shape; it gets one
version.
