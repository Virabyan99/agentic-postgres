# 0109 — The CORS middleware is a label, and it instructs a browser rather than controlling access

Status: accepted
Date: 2026-08-18
Session: 7, Run 7
Amends: [0085](0085-a-route-lives-with-its-backend-and-that-is-the-cheaper-failure.md), [0086](0086-a-rotated-credential-has-to-change-the-parsed-configuration.md)
Affects: STO-URL-001, SEC-API-001

## Context

Nothing in this repository does CORS at the edge today (D323). The storage
surface is the first that needs it: a browser that uploads an object calls
`POST /api/app/storage/upload-intents` from the application's own origin, then
`PUT`s to a presigned R2 URL on a Cloudflare host. Two policies, one origin
list — `storage.allowed_cors_origins`, which has been in the manifest schema and
in the rendered document since Run 1.

The plan (D323) predicted the edge half would be **a Traefik middleware rendered
from the manifest's origin list, in the file provider where a root-owned value
belongs**. Two of the three clauses survive measurement; the third does not.

### What was measured

Two throwaway rigs on the locked Traefik digest, both behind the edge's own
`Label(`apg.traefik.scope`,`managed`)` constraint, with controls.

**A comma-separated origin list in a single label parses into a list.** Read
back from Traefik's own API rather than inferred:

```
m-two@docker    originList=['https://a.example', 'https://b.example']
m-one@docker    originList=['https://a.example']
m-empty@docker  originList=None
```

So a label can express the policy, and the value can travel from the manifest
through `compose.env` as one string. The alternative form — a file-provider
document — was measured working too, in the first rig.

**The middleware answers the preflight itself and never forwards it.** With the
control (`/none`, a router with no CORS middleware) the `OPTIONS` reached the
backend and was echoed; with the middleware attached it did not, for every
origin including a disallowed one.

**It does not refuse a disallowed origin. It omits a header.**

| request | origin | status | `Access-Control-Allow-Origin` | reached the service |
|---|---|---|---|---|
| `GET` | `https://a.example` (listed) | 200 | `https://a.example` | yes |
| `GET` | `https://evil.example` | 200 | **absent** | **yes** |
| `OPTIONS` | `https://evil.example` | 200 | absent | no (answered by Traefik) |

A disallowed origin's *actual* request is forwarded to the service and answered
normally. What stops a browser from using that answer is the browser: it
withholds the response from the page because the header is missing. **A CORS
policy is an instruction to a compliant client, not an access control**, and
`curl` — or any non-browser caller — is unaffected by it in either direction.

**An empty origin list still installs the interceptor.** `originList=None`,
middleware `enabled`, and the preflight is still swallowed. So a project that
enables storage and names no origins gets a middleware that is present and
permits nothing, rather than no middleware — which is the behaviour that makes
attaching it unconditionally safe.

**`Vary: Origin` is on the real responses and absent from the preflight
responses**, even with `addVaryHeader: true`. The preflight's body varies by
origin (the header differs) and carries nothing telling a cache so.

### Why the file provider is the wrong place, measured

ADR 0086 put the documentation credential in the file provider, and the reason —
restated in that module's own docstring — is **a rule about where a secret may
go**: an inline bcrypt hash must not enter Compose interpolation. ADR 0085 had
already measured that the file provider buys nothing for lifecycle, because the
*router* is a label and is withdrawn with its container whatever its middlewares
are doing.

An origin list is not a secret. It is a manifest field, rendered into
`compose.env` and **published in `outputs.json`**. D323's stated reason — "where
a root-owned value belongs" — describes a value this one is not.

And splitting them costs something measurable. A router whose middleware
disappears is not a router that runs without it:

```
router referencing a middleware defined on another container, that container stopped
  -> status=disabled, error=['middleware "rig-app-strip@docker" does not exist']
  -> GET returns Traefik's own 404
```

A file-provider document and the container are two artifacts with two
lifetimes; a label on the storage container has exactly the router's lifetime,
and the two cannot come apart.

## Decision

**The storage CORS middleware is a container label on the `storage` service**,
rendered by `runtime_override._storage_labels` like every other non-secret
middleware this project defines.

**The origin list reaches it as one comma-separated `compose.env` value**,
`STORAGE_CORS_ALLOWED_ORIGINS`, rendered from `storage.allowed_cors_origins` —
the same sorted list the rendered document publishes. One authority, two
renderings, and a test that ties them together.

**It is attached unconditionally**, including when the list is empty, because an
empty list was measured to permit nothing rather than to permit everything.

**The allowed method list is derived from the router**, not written twice. A
contract test compares it against the methods `storage_routes.router` actually
declares.

**It is documented as a browser instruction and never as a control.** Every
statement this repository makes about who may reach the storage surface rests on
the bearer token and the ownership filter, and the docstrings say so where a
reader would otherwise infer an access decision from an allowlist.

## Alternatives

**The file provider, as D323 predicted.** Rejected above: its premise is that
the value is root-owned, and it is not; it adds a second artifact with a second
lifetime; and a missing or misnamed document disables the storage router
outright rather than degrading it.

**Do CORS in the application, with Starlette's `CORSMiddleware`.** Rejected. The
preflight would then require the service to be up and the pool to be open to
answer a request that carries no credential and touches no data, and the policy
would live in the image rather than in the deployment — so changing an origin
would need a rebuild. The edge already terminates TLS and already carries the
response policy that puts `Cache-Control: no-store` on refusals it generates
itself.

**Refuse a disallowed origin at the edge with a 403.** Rejected as a thing this
middleware can do — it cannot; Traefik's `headers` middleware omits a header and
forwards the request. It could be built out of a second middleware, and it would
be **security theatre**: the same request without an `Origin` header is
indistinguishable from a server-side caller, which is a legitimate and supported
way to use this API.

## Consequences

* **The login that produces a storage token is not itself reachable
  cross-origin.** `/api/app/auth/login` carries no CORS middleware and there is
  no `api.app.allowed_cors_origins` field, so a browser-only flow — log in from
  a page, then upload — is not possible today. Recorded as D356 rather than
  fixed: a second origin list is a manifest change and a decision about the auth
  surface, and the alternative reading (the application logs in server-side and
  hands the browser a token) needs no CORS on `/auth` at all. Neither reading is
  this run's to choose.
* A cache between a browser and the edge could serve one origin's preflight
  response to another, because the preflight carries no `Vary`. There is no such
  cache in this deployment. Recorded so the next person to put one there knows.
* The R2 half of the policy is provider configuration and is Run 8's. Both are
  rendered from `storage.allowed_cors_origins`; nothing may introduce a second
  list.
