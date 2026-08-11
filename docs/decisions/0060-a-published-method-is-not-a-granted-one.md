# 0060 — A published method is not a granted one, and the snapshot records what is served

Status: accepted
Date: 2026-08-11
Session: 5, Run 7
Affects: API-CONTRACT-001, API-SCHEMA-001, API-RPC-001

## Context

`contracts/postgrest-api-surface.yaml` declares `methods: [GET, HEAD]` on both
relations, and `api_surface.validate_surface` refuses any other method with a
reason: a table-style write on a view would let a caller name the `owner_id` it
likes and satisfy the row policy by saying so.

`API-CONTRACT-001` compares the committed snapshot against that contract. The
obvious comparison is method-for-method — the contract says `[GET, HEAD]`, the
document lists what the document lists, and they should agree.

They do not, and neither side is broken. Measured against the locked PostgREST
14.16, with a role holding `SELECT` on `api.notes` and nothing else — the grant
read back out of `information_schema.role_table_grants`, not assumed:

| | |
|---|---|
| Granted | `SELECT` |
| Published in OpenAPI | `delete`, `get`, `patch`, `post` |
| `HEAD /notes` | **200**, and **not published** |
| `POST` / `PATCH` / `DELETE /notes` | **403**, `42501 permission denied for view notes` |

`openapi-mode = follow-privileges` filters the **path**, not the **methods on
it**. The path appears because the role can read the relation; the method list
is derived from what the relation is — an updatable view — rather than from what
this caller may do to it. Run 5 already measured the path half of this
(`test_a_role_with_no_grant_sees_no_relation`); the method half was never asked
about, because a document that filters by privilege is assumed to filter by
privilege.

So the published document is wrong in both directions at once: it advertises
three methods the database refuses, and omits one it serves.

## Decision

**The snapshot records what is served. The contract's methods are compared
against the catalog, and never against OpenAPI.**

Three consequences, and the ordering is §6's:

1. `bin/api-contract.sh --check` compares the snapshot and the surface contract
   **at the level of objects** — which relations and which RPCs are published —
   and not at the level of methods. An object in one and not the other is a
   failure; a method list is not compared, because the two sides are answers to
   different questions.
2. `methods:` in the surface contract is enforced where it is *true*: against
   the catalog ACLs (authority 2), by `API-RPC-001`, which attempts each
   refused method and asserts the 403 rather than reading a document about it.
3. The extra methods are **not stripped during normalization.** The snapshot's
   whole function is to be the client contract — the document a generator will
   actually be pointed at. A snapshot that differs from the served bytes is a
   snapshot that describes a service nobody deployed.

## Consequences

**Every generated client will offer `DELETE /notes`, and calling it returns
403.** That is a documentation defect this deployment cannot configure away:
there is no PostgREST setting that filters methods by grant, and the alternative
— revoking the view's updatability by rebuilding it as non-updatable — would
change the schema in order to tidy a document, which is the shape ADR 0058
already refused. It is recorded here so the next reader finds a measurement
rather than a surprise, and so the documentation page's own text can say it.

**`HEAD` being absent from the document is harmless and is still written down.**
It is served, the contract names it, and a client generated from the snapshot
will not offer it. The asymmetry is the same fact from the other side: the
method list is a property of the relation, not of the caller.

**The comparison that remains is the one that can fail usefully.** An object
present in `api` and absent from the contract is a release failure even when its
grants keep it out of OpenAPI (ADR 0050), and that check is unaffected — it runs
against the catalog. What this ADR removes is a comparison that could only ever
have failed, and whose repair would have been to widen `methods:` to
`[GET, HEAD, POST, PATCH, DELETE]` — turning the reviewed read-only surface into
a permissive one, in a file whose entire function is to be narrower than the
catalog.

## Alternatives considered

**Compare methods, and widen the contract to the published set.** Rejected, and
it is the alternative worth naming because it is what a green-test-at-any-cost
repair looks like. It would make `api_surface`'s refusal of table-style writes
unreachable, and the file that exists to disagree with the catalog would have
been edited to agree with a document instead.

**Strip the unreachable methods during normalization.** Rejected. It produces a
committed document that no deployment serves, so the snapshot stops being the
thing a client is generated from, and `--check` against a live document would
have to strip before comparing — which means the check could no longer notice
the day the published method set changes.

**Rebuild the views as non-updatable so PostgREST publishes fewer methods.**
Rejected on ADR 0058's precedent: changing the schema to alter a generated
document is the tail wagging the dog, and a non-updatable view would also
foreclose a later session adding a properly-mediated write.
