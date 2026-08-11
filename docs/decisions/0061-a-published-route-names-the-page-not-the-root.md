# 0061 — A published route names the page, not the root above it

Status: accepted
Date: 2026-08-11
Session: 5, Run 8 (found preparing Run 9)
Amends: [0002](0002-configuration-authority.md), [0053](0053-outputs-version-5.md)
Affects: SEC-DOCS-001, SEC-API-001

## Context

Two files in this repository state where the REST documentation page lives, and
they do not agree.

```
src/agentic_postgres/naming.py:412   route_docs = f"https://{domain}/docs"
src/agentic_postgres/config.py:227   DOCS_REST_PATH = "/docs/rest"
```

`route_docs` is what `rendering.py` writes into `outputs.json.routes.docs`, and
what `deployed_output.py` copies onto the deployed branch with a status. So it
is the value `bin/docs.py` requests, the value `SEC-DOCS-001` requests, and the
value `SEC-API-001` asserts refuses without a credential — `outputs.json` being
the one document everything reads a route from (ADR 0002).

`DOCS_REST_PATH` is what Run 6 measured against the locked Traefik and what
`tests/contract/test_edge_behaviour.py` builds its router from:

```
rule: "Host(`probe.test`) && (Path(`/docs/rest`) || PathPrefix(`/docs/rest/`))"
```

401 without a credential, 200 with it, `Authorization` stripped before the
upstream — all measured at `/docs/rest`. It is also what
`config._validate_route_boundaries` proves pairwise distinct from the REST and
MCP prefixes.

**The product has no documentation router yet.** Run 9 is the run that publishes
one, and it would have published it at `/docs/rest`, because that is the only
path anything has measured. The deployed document would have gone on recording
`routes.docs = https://<domain>/docs` with `status: ready`.

The consequence is not subtle once it is written down. In Run 9, `bin/docs.sh
check` requests `/docs`, reaches no router, and reports **404, not 401** — which
its own code correctly refuses to treat as a refusal. `SEC-API-001` asserts
`status == 401` on the same URL and fails. Both failures would have been read as
a broken edge in the middle of a maintenance window, and neither is about a
boundary.

The worse ordering is the one that does not fail. If anything is ever served at
the reserved `/docs` root without the credential middleware — a Session 11 index,
say — then `routes.docs.status: ready` becomes a true statement about a page
that is **not** the one this session protects, and the documentation boundary is
recorded as measured against a URL nobody checked.

`deployed_output.py` already contains the tension, resolved the wrong way, in a
comment:

> `routes.docs` is the documentation root the rendered branch has carried since
> Session 1, and the REST documentation page lives under it — so the status
> recorded here is the status of the page this session publishes, not a claim
> about a root reserved for a later index.

A status about the page, attached to the URL of the root.

## Decision

**`routes.docs` names the page: `https://<domain>/docs/rest`.**

The path is derived once, in `naming.py`, which ADR 0002 makes the single
authority for every route. `config.DOCS_REST_PATH` keeps its name — the manifest
layer compares prefixes and must not import a URL to do it — and becomes a read
of `naming.DOCS_PAGE_PATH` rather than a second literal.

`test_naming.py::test_routes_are_derived_from_the_domain` is **replaced by a
stricter assertion**, not weakened: it now asserts the documentation route names
the page Run 6 measured, and asserts it against `naming.DOCS_PAGE_PATH` rather
than a repeated string.

The two rejected alternatives:

**Publish the router at `/docs` instead.** It would make the two agree, and it
would discard Run 6's measurement — the only measurement anybody has of this
route — in favour of a string. `/docs` also stays reserved for Session 11's
index (`RESERVED_BASE_PATHS`), so this would put the one page Session 5 protects
at the root a later session wants to own, and Session 11 would have to move it.

**Add a second field, `routes.docs_rest`, and leave `routes.docs` as the root.**
This preserves the field's Session 1 meaning at the cost of an outputs schema
bump and a field that reads `unavailable` for every project until Session 11
builds an index. It also leaves `routes.docs` in the document as a URL with a
status and nothing serving it, which is exactly what the `publishedRoute` schema
was tightened in version 5 to prevent: *a record that claims to exist and points
at nothing*.

No schema bump is needed. `routes.docs.url` is an `httpsUrl` on both branches and
`/docs/rest` is one; nothing about the shape of either document changes.

Documents rendered before this change keep `/docs`, and that is correct — a
rendered document records what that render produced. Nothing migrates a route
URL.

## Consequences

- Run 9 publishes the documentation router from `outputs.json`, like every other
  route, rather than from a constant a run had to choose.
- `bin/docs.sh check`, `SEC-DOCS-001` and `SEC-API-001` request the page the edge
  serves. All three were pointed at the root before this.
- The reserved `/docs` root is still reserved and still refuses a manifest that
  collides with it. It is simply no longer published as a ready route by a
  session that serves nothing there.
- One derivation of a route path, which is what ADR 0002 says and what this
  repository had two of.

`REST_PATH_SUFFIX` is the same shape and was already the same hazard — a path
constant in `config.py` held "in step with" `naming.derive`. It is folded into
the same single authority here rather than left as the next instance.
