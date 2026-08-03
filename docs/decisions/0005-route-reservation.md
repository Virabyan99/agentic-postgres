# 0005 — Reserved routes and segment-wise overlap

- **Status:** Accepted
- **Date:** 2026-08-03
- **Session:** 1
- **Affects:** `CFG-011`

> Transcribed 2026-08-04 from decision **B** of
> [the Session 1 implementation plan](../plans/session-01-implementation-plan.md).
> The decision was made and implemented in Session 1; only this record was
> missing, and `src/agentic_postgres/config.py` cited it as its source of
> truth. The decision date above is the date of the decision, not of the file.

## Context

Runbook §3.4 requires a project's `api.public_base_path` and
`mcp.public_base_path` to be rejected when they collide with a reserved route
or with each other, and calls the failure condition "ambiguous overlap" without
defining either the reserved set or the overlap relation.

Both halves have to be decided before validation can be written, and the
obvious implementation of the second half is wrong. `str.startswith` would
reject `/apiv2` against `/api` — two genuinely distinct routes that no router
would ever confuse — while a naive segment comparison that ignored equality
would let a project claim `/api` twice.

## Decision

**Reserved base paths** are exactly:

```
/docs  /health  /healthz  /ready  /metrics
/.well-known  /traefik  /static  /favicon.ico  /robots.txt
```

Each earns its place: `/docs` is derived unconditionally by runbook §3.8, so it
is structurally reserved; `/.well-known` is the ACME HTTP-01 challenge path,
needed from Session 2; `/health`, `/healthz`, `/ready` and `/metrics` are the
`OPS-001` surface; the rest are conventional edge-router paths that would
silently shadow a project route rather than fail loudly.

**Root is deliberately absent from that tuple.** Under the overlap relation
below every path is a descendant of `/`, so including it would reject all
input. `/` is rejected instead by an explicit equality check in
`_validate_base_path`, which produces a message about the actual problem.

**Overlap is decided segment-wise.** A base path normalizes to its tuple of
non-empty segments — `/api/v1` → `("api", "v1")`. Two paths overlap **iff one
tuple is a prefix of the other, including equality.** The same relation is
applied between the two project base paths and between each of them and every
reserved path.

Consequences of that definition, all tested:

| Pair | Overlaps? |
|---|---|
| `/api` vs `/api/v1` | yes — prefix |
| `/api` vs `/api` | yes — equality |
| `/api` vs `/apiv2` | **no** — different first segment |
| `/mcp` vs `/docs` | no |

## Consequences

Makes easy:

- The rule is stated once and applied three ways, so reserved-route collision
  and api/mcp collision cannot drift apart.
- `/apiv2`, `/api-internal` and similar remain available, which matters because
  the slug space is narrow and operators will reach for suffixes.

Makes hard:

- Adding a reserved path is a source change with a test, not configuration.
  That is intended — a reserved path is a promise the platform makes about a
  route it will one day own.
- The tuple is not exposed in `project.yaml`. A deployment cannot un-reserve
  `/metrics` locally, which is the point.

Enforced by `RESERVED_BASE_PATHS` and `paths_overlap()` in
`src/agentic_postgres/config.py`, and by
`tests/contract/test_project_manifest.py::test_reserved_route_collision_is_rejected`,
`::test_api_and_mcp_trees_may_not_overlap`, and
`::test_similar_but_distinct_prefixes_are_allowed`. The third of those is the
one that fails if anybody reimplements this with `startswith`.

## Alternatives considered

**String prefix matching.** Rejected: rejects `/apiv2` against `/api`. The
failure is silent in the sense that it looks like correct behaviour until an
operator hits it, and then it looks like a bug in the wrong place.

**Reserving `/` in the tuple.** Rejected: makes every input overlap. Handled by
an explicit equality check instead, which also yields a better message.

**Reserving nothing and letting Traefik resolve precedence.** Rejected: Traefik
would resolve it, deterministically and invisibly, in favour of whichever
router had the longer rule. A project would then silently lose `/metrics` to
the platform with no error anywhere.
