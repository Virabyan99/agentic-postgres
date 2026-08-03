# 0015 — The platform health route is reserved

- **Status:** Accepted
- **Date:** 2026-08-04
- **Session:** 2
- **Affects:** `CFG-011`, `DEP-EDGE-001`, `DEP-EDGE-002`, `OPS-TLS-001`

Amends [0005](0005-route-reservation.md), which fixed the reserved set in
Session 1.

## Context

Session 2 needs one HTTPS route per project that the edge plane can be proved
through: a deterministic target that exists before any application service, so
that "Traefik routes this project, with a trusted certificate, and returns this
project's identity" is a measurable claim rather than a story about a future
service. That is the edge probe, and it answers at a fixed path.

The path has to be fixed rather than configurable, because the Session 2 gate,
the external suite, the deployed document and the operator guide all name it,
and a configurable value would have to be threaded through all four.

Which creates a collision the schema does not currently prevent. A project's
`api.public_base_path` is constrained only by `^/[^/].*[^/]$|^/[^/]$`, so a
manifest can legitimately claim any path — including the health route. If it
did, Traefik would resolve precedence between two routers deterministically and
invisibly, and the project would either shadow the probe or be shadowed by it.
Either way the gate would be measuring something other than what it names.

## Decision

**The platform health route is `/__apg/healthz`,** declared once as
`naming.HEALTH_ROUTE_PATH` and derived per project as
`https://{domain}/__apg/healthz`.

**`/__apg` is added to `RESERVED_BASE_PATHS`.** Under 0005's segment-prefix
overlap relation, that rejects a project claiming `/__apg` or anything beneath
it, and leaves `/__apgx` available — the same distinction 0005 exists to draw.

**The prefix is `/__apg`, not `/health`.** `/health` is already reserved, but
reserving a *namespace* rather than a bare word buys two things: every future
platform route lands under one prefix that operators can recognize and firewall
as a unit, and the platform stops competing with applications for ordinary
English path names. The double underscore is conventional for "this belongs to
the framework, not to you", and it is unlikely to be chosen by accident.

`routes.health` appears in the rendered document as `{status: "planned", url}`
and in the deployed document as `{status: "ready"|"unavailable", url}`, per
[0012](0012-output-document-kinds.md).

## Consequences

Makes easy:

- The Session 2 gate names one URL shape for every project, and the external
  suite can construct it from the deployed document alone.
- A future platform route — a readiness endpoint, an ACME helper, an ops probe —
  goes under `/__apg/` with no further reservation and no new collision.
- The collision is caught at manifest validation, with a message naming the
  reserved path, rather than at runtime as a router-precedence surprise.

Makes hard:

- A project genuinely wanting `/__apg` cannot have it. Deliberate, and cheap:
  the name was chosen partly because nobody wants it.
- The reserved set is now a Session 2 concern as well as a Session 1 one, so
  0005 has an amendment rather than a single frozen list. Recorded here rather
  than by editing 0005, per the numbering rule.

Enforced by `RESERVED_BASE_PATHS` in `src/agentic_postgres/config.py` and by a
test asserting a manifest claiming `/__apg` is rejected while `/__apgx` is
accepted.

## Alternatives considered

**Reserve `/healthz` and route the probe there.** Rejected: `/healthz` is
already reserved but it is a bare word an application may want, and it says
nothing about who owns it. It also gives no home to the next platform route.

**Make the health path configurable in `host.yaml`.** Rejected: it would have to
be threaded into the gate, the external suite, the deployed document and the
operator guide, and every one of those would need a fallback for the default.
Configurability with one sensible value is a cost with no buyer.

**Rely on Traefik router priority instead of reservation.** Rejected: priority
resolves the collision silently and correctly, which is the problem. The
operator learns their route was shadowed by observing that it does not work.

**Route the probe on a separate hostname.** Rejected: it needs a second DNS
record and a second certificate per project, and it would prove the edge plane
works for a hostname no project actually uses.
