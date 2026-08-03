# 0007 — The project schema is the sole authority for numeric bounds

- **Status:** Accepted
- **Date:** 2026-08-03
- **Session:** 1
- **Affects:** `CFG-001`, `CFG-010`, and the generated bounds table in the product contract

> Transcribed 2026-08-04 from decision **E** of
> [the Session 1 implementation plan](../plans/session-01-implementation-plan.md).
> The decision was made and implemented in Session 1; only this record was
> missing.

## Context

Runbook §3.5 states numeric bounds for the project manifest — connection
counts, pool sizes, row limits, byte ceilings, URL lifetimes — and they appear
in three places that all want to be authoritative: the JSON Schema that
validates the manifest, the semantic validation code that produces error
messages, and the operator-facing table in `docs/product-contract.md`.

Three hand-maintained copies of the same number drift, and the drift is worse
than a plain bug: the documented bound and the enforced bound disagree, so an
operator reads one number, hits another, and has no way to tell which is
correct.

## Decision

**`schemas/project.schema.json` is the sole authority.** Every bound is
expressed natively as `minimum` / `maximum` / `maxLength`.

Three consequences follow, and all three are enforced:

1. **Semantic validation code restates no bound.** There are no numeric bound
   literals anywhere in `src/`. When `config.py` needs a bound value for an
   error message, it loads the schema once and reads it.
2. **The documentation table is generated,** into a marker-delimited block in
   `docs/product-contract.md`, by `bin/render-config.py --bounds-doc --write`.
   `--bounds-doc --check` regenerates into memory and byte-compares; it never
   writes. The gate and CI run `--check` only, because the gate demands a clean
   tree in step 1 and a self-healing generator would dirty the tree it just
   required be clean. `.pre-commit-config.yaml` runs `--write` so drift is
   corrected at commit time and the gate only ever confirms.
3. **Cross-field relations are not bounds and live in code.** JSON Schema
   cannot express a comparison between two properties, so
   `database.pool_size <= database.max_client_connections`,
   `mcp.max_result_rows <= api.max_rows`, the two base-path overlap rules of
   [0005](0005-route-reservation.md), and the public-CIDR rule live in
   `CROSS_FIELD_RELATIONS` in `src/agentic_postgres/config.py` — as **data**,
   so the same generator emits them into the same documentation block rather
   than a human restating them.

## Consequences

Makes easy:

- Changing a bound is one edit. The documentation follows mechanically and the
  gate proves it followed.
- A reviewer reading the schema is reading the thing that actually runs.

Makes hard:

- Error messages cost a schema lookup rather than a module constant. Measured
  and irrelevant; the schema is already loaded.
- A bound that JSON Schema genuinely cannot express has to become a relation in
  `CROSS_FIELD_RELATIONS` rather than a quiet `if` in a validator. That is the
  point of the split: the second list is short, visible, and generated into the
  documentation alongside the first.

Enforced by `bin/render-config.py --bounds-doc --check` in
`bin/session-01-check.sh` step 6 and in CI.

## Alternatives considered

**A Python module of constants as the authority, with the schema generated from
it.** Rejected: the schema is the only one of the three artifacts that is
machine-consumed at validation time. Making anything else authoritative
guarantees that the enforced value and the stated value can differ — which is
the exact failure being designed out.

**Parsing the markdown table to check it against the schema.** Rejected:
parsing hand-written markdown is fragile in precisely the way that produces a
false green. Generating the table makes the mismatch structurally impossible
rather than merely detectable.

**Leaving the documentation hand-written and accepting drift.** Rejected: the
bounds table is the operator-facing contract. A wrong number there is a support
burden that looks like a product defect.
