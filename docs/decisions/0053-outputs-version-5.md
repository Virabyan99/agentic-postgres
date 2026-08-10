# 0053 — Outputs version 5: the deployed document carries the public surface and the identity the broker needs

Status: accepted
Date: 2026-08-10
Session: 5, Run 1
Extends: [0012](0012-output-document-kinds.md), [0027](0027-the-output-schema-gains-a-version-and-a-migration-path.md), [0041](0041-two-transports-three-access-profiles.md)
Affects: API-CONTRACT-001, SEC-BOOT-001, SEC-API-001, DX-DB-002

## Context

Two things need somewhere to live, and one of them has been waiting a session.

**The public API surface.** Session 5 serves a REST route and a documentation
route, and a reader has to be able to answer "what is published, is it ready,
and which reviewed contract is it serving" without running anything.

**The identity the access broker needs.** D106 recorded it and deferred it here
in so many words: the port-allocation registry is keyed by
`app_private.project_identity.instance_uuid`, and its own module docstring says
the project key is recorded for humans and is *never* the match key. The
deployed document records no instance UUID, so the broker searches live
allocations by project key and refuses ambiguity rather than resolving it. A
first match there is a credential handed out for the wrong cluster, and nothing
downstream would notice: the port answers, the role exists, the password
authenticates.

The v4 schema is closer to both than it looks. `routes.rest` and `routes.docs`
are already required on the **rendered** branch, `jwt.issuer` and `jwt.audience`
with them. What the **deployed** branch has is `routes` containing only
`health` — which Session 2 built as a status-carrying object with a stated
reason: "an object rather than a bare URL so the rendered and deployed branches
stay structurally parallel: the deployed document has to carry a readiness
claim, and a claim needs somewhere to live."

That is this session's requirement, written three sessions early.

## Decision

**Version 5 extends what exists. It does not add a parallel block.**

On the **deployed** branch:

- `routes` gains `rest` and `docs`, each shaped like `health`: a `status` of
  `ready | unavailable` and a URL. `unavailable` forces the same nulls the
  endpoint definition already forces, so a route that claims to be serving and
  names nothing cannot validate.
- A new `api` object carries the observed exposed schema, the row ceiling, the
  body limit, the pool size and reserved budget, and three checksums — the
  API-surface contract, the canonical snapshot, and the per-project snapshot
  actually published.
- `jwt` appears on this branch for the first time, carrying **public metadata
  only**: issuer, audience, algorithm, active `kid`, the ordered verification
  `kid` set, the public JWKS checksum, `temporary`, and a retirement deadline
  when a rotation is in flight (ADR 0051).
- `database.observed` gains `instance_uuid`, and `libexec/database-access`
  switches to matching on it. The project key stays in the registry for humans,
  as its docstring has always said.

Rendered `routes.rest` and `routes.docs` are unchanged and remain the single
derivation of those URLs; the deployed branch records status and observation
against them rather than restating them from a second source.

**No direct service address is emitted.** `postgrest:3000` is a runtime
implementation detail; public and client traffic uses the Traefik route so the
edge's body limits and policy cannot be bypassed. No admin URL is emitted
because the admin surface is not a network service. No token, password, private
JWK, credential-bearing URL or documentation credential appears — `httpsUrl`
already forbids a userinfo component, so this is structural rather than a rule
someone must remember.

The full D40 price is paid: a `v4 → v5` function in `output_migrations.py`, a
committed `tests/fixtures/outputs-v4.json`, and the standing rule that migration
never produces a *deployed* document.

## Consequences

**A reader answers the Session 5 question from one file.** `jq '.routes, .api,
.jwt'` says what is published, whether it is ready, which contract it serves and
whether the issuer is still the temporary one.

**The broker stops guessing.** Two live allocations under one project key was
exit `5` because there was nothing better to do; with the UUID in the document
there is, and the refusal becomes an assertion that the two agree.

**One URL, one record.** A parallel `http_api.rest.public_url` beside
`routes.rest` would be two records of one value, and this repository has watched
such a pair drift — most recently in Session 4, where an endpoint's port and its
URL's port are compared for equality by a test written after they nearly did.

**`temporary` is readable by a later gate.** Session 6 does not have to remember
to retire the bootstrap issuer; `SEC-BOOT-001` reads this field against
`deployed_through_session` and goes red on the deployment that should have
replaced it (ADR 0051).

**Every deployed document on the host stops validating until it is rewritten.**
That is the third time — v2, v3, v4 — and the handling is unchanged: nothing the
host *executes* validates the version, so nothing breaks before the redeploy,
and the redeploy is what makes the host's state readable by this code again.

## Alternatives considered

**The runbook's top-level `http_api` block.** Rejected: it duplicates
`routes.rest`, and the duplicate is the deployed branch's only copy — so the
rendered and deployed branches would name the same URL under two different
paths. `routes` exists, is required on both branches, and was built with a
status-carrying member for exactly this.

**Put the API observation under `database.observed`.** Rejected: that block is
defined as measurements of a running *cluster*, and a route's readiness is not
one. Keeping it means `observed` stays answerable by one probe against one
service.

**Defer `instance_uuid` again.** Rejected. It has been deferred once with a
written reason, the schema is being versioned anyway, and the cost of carrying
it is one field against the cost of a broker that resolves a credential by
first match on a key its own registry says is not a key.

**Emit the direct service address for convenience.** Rejected: it is the one
field that would let a client bypass the edge, and a supported endpoint is one
somebody eventually depends on.
