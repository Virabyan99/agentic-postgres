# 0069 — The documentation page is a first-party build under our own CSP

Status: accepted
Date: 2026-08-12
Session: 5, Run 9a
Settles: D128
Affects: SEC-DOCS-001, SEC-API-001, DEP-ISO-005

## Context

D128 left the documentation service's shape open and named the measurement that
would decide it: *does the Scalar bundle produce a self-contained artefact with
no runtime fetch?* The plan recorded the question as settled in Run 1. No ADR
recorded an answer and nothing implemented one, so `services/docs/` has been a
`.gitkeep` and `routes.docs` publishes `null` — which is what both remaining
live failures land on.

Two things were measured, and neither is what the row expected.

**The pinned version does not exist** (D201). `SCALAR_VERSION: "1.36.4"` has been
in `versions.in.yaml` since Session 1; `@scalar/api-reference` published 1.36.2
and then 1.37.0, and no Scalar image carries the tag either. It survived four
sessions because `bin/lock-versions.sh` resolves `images:` against a registry
while a `packages:` entry is a string nothing dereferences.

**Self-containment is not a discriminator** (D202). Measured on both real
candidates, `dist/browser/standalone.js` names `fonts.scalar.com` fourteen times
and `proxy.scalar.com` beside it, and `withDefaultFonts` is declared
`default: true` — at 1.36.2 and at 1.64.1 alike. The bundle fetches from a third
party unless configuration says otherwise, whatever ships it. So the question
D128 posed cannot separate an upstream image from a first-party build: both must
configure their way out of the same default.

Worse for the proof D142 promised: the hostnames stay in the bytes whether the
switch is on or off. A scan for external hosts in the served files fails on a
correctly configured page.

## Decision

**`services/docs/` is a first-party build, and the page is served under a
Content-Security-Policy this deployment sends.**

The distinction that decides it is not self-containment but *who owns the
response*. `withDefaultFonts: false` is a promise about a third party's code
honouring its own flag. `default-src 'none'; script-src 'self'; font-src 'self';
connect-src 'self'` is a rule the visitor's browser enforces against whatever
the bundle attempts. Only the second is a property of this deployment, and only
a build we own can send it — an upstream image's headers are the vendor's, and
moving the CSP to Traefik would put it a hop away from the bytes it governs.

Four consequences of that, each measured on the built image:

1. **Two stages, one file crosses.** The build installs 230 MB from a committed
   `package-lock.json` with `npm ci --ignore-scripts` and copies exactly
   `standalone.js` out. The shipped image is **42 MB**.
2. **The server is a route table, not a static file server.** Four paths, GET and
   HEAD. There is no path joining, no directory walk and no content negotiation,
   which is a shorter argument than any traversal defence because there is no
   path to traverse. Measured: `/../serve.py` and `/app/serve.py` are 404,
   every other verb is 501.
3. **The snapshot is mounted, not baked.** `contracts/postgrest-openapi.canonical.json`
   is the artefact a human approved; baking it would mean an image per project
   per revision, each a place the reviewed bytes could differ from the reviewed
   bytes. Measured: what the route serves is byte-identical to the committed
   file. An unreadable mount is **503**, never an empty document — an empty
   OpenAPI file is valid and describes nothing.
4. **The page says what the surface does.** ADR 0060: the document advertises
   `DELETE`, `PATCH` and `POST` on both views and all three return 403, and no
   setting filters methods by grant. The page carries that in its own text,
   above the reference, or the documentation is the first thing here that lies
   about the surface.

`SCALAR_VERSION` is re-pinned to **1.64.1**, chosen over 1.36.2 because there is
no intent to honour: the old number was not a decision anybody made.

## Alternatives

**The upstream image** (`scalarapi/api-reference`). Rejected on two measurements.
It publishes **`latest` only** — no version tags — so the lock would record a
digest with no version identity, which is what ADR 0004's format and D127's
no-floating-tag rule exist to prevent. And its served bytes and headers are the
vendor's, so the CSP would have to be applied at the edge, one hop from what it
governs, while `SEC-DOCS-001`'s byte scan would run over bytes we did not write.

**A CSP at Traefik instead of at the service.** Rejected as the *only* location,
not as an addition: a header applied by the router is absent the moment something
reaches the service by another path, and this service is on a project network
with a REST plane beside it.

**Trusting `withDefaultFonts: false` alone.** Rejected: it is a third party's
flag, and D202 is the measurement showing the default is the unsafe one. It is
still set — belt and braces, with the header as the braces.

## Consequences

- `routes.docs` can become ready, which unblocks `SEC-DOCS-001` and
  `DEP-ISO-005`. Neither passes until the service is wired into `compose.yaml`
  and the deploy publishes the router; this ADR settles the shape, not the
  wiring.
- A fifth first-party build context, and the first that vendors a third-party
  browser bundle. The lock file is committed and `npm ci` fails if it and
  `package.json` disagree.
- **`style-src` carries `'unsafe-inline'`**, knowingly. Scalar writes component
  styles into the document at runtime and the page renders unstyled without it.
  It is bounded by `default-src 'none'` — an inline style cannot fetch, navigate
  or execute — and by `script-src` carrying no such allowance, which is where the
  risk would actually live.
- **A credential scan must look for values, not vocabulary.** The vendored bundle
  matches `password|secret|bearer` **34 times** in its own auth-UI text, so a
  keyword scan over served bytes fails on a correct page. `SEC-DOCS-001` already
  scans for the materialized secret and for `Bearer ey`/`eyJhbGciOi`, which is
  the right shape; this records why it must stay that way.
