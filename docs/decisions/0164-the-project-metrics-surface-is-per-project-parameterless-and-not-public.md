# 0164 — The project metrics surface is per project, parameterless, and not public

- **Status:** accepted
- **Date:** 2026-09-01
- **Session:** 14, Run 2 (`OPS-METRIC-001`, D760)
- **Related:** **D760** (the route was reserved in Session 1 and never
  redeemed), **D768** (measured: Traefik serves metrics at the deployed digest,
  and a 404 from that endpoint means two different things), **D769** (measured:
  the exported family set grows with traffic), **D770** (measured: a store sizes
  its caches from the machine it lands on), **D772** (measured: the baseline
  middleware chain was attached by enumeration and lost a middleware),
  ADR 0005 (the reservation itself), ADR 0002 (one derivation per identity),
  ADR 0085/0086 (the documentation credential and where a secret may go),
  ADR 0042/0043 (the deployment's other "not public by default" surfaces).

## Context

ADR 0005 reserved `/metrics` in Session 1 and called a reserved path *"a promise
the platform makes about a route it will one day own."* Thirteen sessions later
nothing owned it: `/metrics` appears exactly once outside the tests, as a string
in `RESERVED_BASE_PATHS`. Session 14 redeems it, and three questions have to be
answered before a route can exist.

**What serves it.** The obvious answer — point the route at the metrics store
and let a caller federate — does not work, and the reason is mechanical rather
than aesthetic. Prometheus's `/federate` and VictoriaMetrics' equivalent both
**require a `match[]` query parameter**, and Traefik has no middleware that can
add a query string to a request. A route that needs a parameter the edge cannot
supply is a route whose caller has to know the store's query language, which
makes the reservation's promise into an operator's homework.

**Who may read it.** A metrics surface is a description of a deployment's
internals: how many connections, which errors, how far behind the archiver is.
The reserved path sits under the project's own hostname, behind the same edge as
everything else, so "published" and "public" would be the same thing unless
something is done about it.

**Whose metrics.** The naming plane derives every identity per project
(ADR 0002). A single host-scoped store would be the one process in this
deployment where two projects' data coexist, separated by a label rather than by
a topology — which is the opposite of how isolation is done everywhere else
here, and Session 12's matrix proved isolation over 179 leaves precisely because
it is structural.

## Decision

**One metrics surface per project, at the reserved path, served by that
project's own collector, behind a credential.**

**1. The route is `/metrics` under the project's own host**, claimed from
`RESERVED_BASE_PATHS` rather than added to it. Nothing about the reserved tuple
changes; this is the redemption of a promise already made, and a project still
cannot claim the path itself.

**2. Its backend is the project's OpenTelemetry collector, not its store.** The
collector's `prometheus` exporter serves Prometheus exposition **with no query
parameters**, which is what makes an edge route possible at all. Measured
against `otel/opentelemetry-collector-contrib`, with a control whose scrape
target does not exist:

| Arm | Response | `traefik_*` series |
|---|---|---|
| collector scraping the real Traefik | 200, 20,513 bytes | 4 |
| **control** — identical, target does not resolve | 200, 1,896 bytes | **0** |

The control is the point. A 200 alone would not distinguish *serving the
project's metrics* from *serving the collector's own*, and the second would be a
surface that describes nothing anybody asked about. `/` on the same port is 404,
so the exporter serves one path and needs no prefix rewriting.

**3. The store scrapes the collector over the project's internal network and is
never routed at the edge.** This falls out of (2) rather than being a second
decision: because the collector already holds the project's current metrics in
exposition form, the store is a consumer of it like any other. **So the store
holds no edge credential** — which is the property that made this shape
preferable to routing the store directly, where every scraper would need one.

**4. The route is not public.** It carries a basic-auth middleware in the same
shape as the documentation route: one credential, materialized per project into
an immutable generation, the bcrypt hash inline in a per-project file-provider
document (ADR 0086), never in a label and never in Compose interpolation. The
documentation route is the precedent and the mechanism is reused rather than
re-derived. `OPS-METRIC-001`'s second half is a 401 without the credential.

**5. Everything is per project.** Collector, store, credential, router,
middleware and network membership are derived per project through `naming`, like
every other identity. Two projects share the edge and nothing else.

**6. The collector and the store each carry an explicit container memory
limit.** See ADR 0165, which is the general form of this and applies to any
telemetry component this repository deploys.

## Consequences

Makes easy:

- The reservation means what ADR 0005 said it meant, and the path is owned by
  the platform on the terms it was reserved on.
- An external monitoring system federates by scraping one authenticated URL per
  project, in a format every such system reads, with no knowledge of which store
  is behind it. Replacing the store later changes nothing a caller sees.
- Two projects' metrics cannot meet, because they are never in one process.
- A metric added in a later run appears at the edge without a route change.

Makes hard:

- **Two collectors and two stores rather than one of each.** Measured: about
  52 MB of anonymous memory per project, against 2,110 MB available on a host
  whose eighteen containers hold 573.8 MB in total. Bought deliberately, and the
  numbers are in D767 and D770 rather than in an assurance.
- A scraper must hold a credential per project. That is the cost of the route
  being authenticated, and it is the reason the store — which scrapes far more
  often than any human — was kept off the edge entirely.
- **`opentelemetry-collector-contrib`, not the core distribution.** The
  `prometheus` receiver and exporter are both contrib-only. Measured: 31.1 MB
  anon against core's 14.3 MB, and a 103.6 MB image against 35.0 MB.

Residuals, named rather than implied:

- **A 404 from this route means two things** (D768). Traefik's metrics
  entrypoint answers 404 for ~144 ms at startup, before its internal router is
  installed, and answers 404 for ever when metrics are not configured. Nothing
  that checks this surface may read a status code alone; the proof reads the
  body.
- **The exported family set grows with traffic** (D769), so a freshly deployed
  project serves fewer families than a busy one. That is a property of the
  upstream exporters, not of this route, and it is what Run 5's alert rules must
  say something explicit about.
- The collector is reachable from the project's internal network. It is **not**
  reachable from the backup egress network, and nothing here adds a second path
  off the host (ADR 0147's residual is not widened).

## Alternatives considered

**Route `/metrics` at the store's federation endpoint.** Rejected on a
measurement rather than a preference: `match[]` is required and no Traefik
middleware can add a query parameter. Working around it would mean a rewriting
proxy in front of the store — a component whose whole job is to add a constant
string to a URL.

**Publish the route unauthenticated.** Rejected. The surface enumerates
connection counts, error rates and archiver lag per project; ADR 0042 and
ADR 0043 both decided that this deployment's diagnostic surfaces are reached
deliberately rather than by anyone who knows the hostname.

**An IP allowlist instead of a credential.** Rejected for a specific reason: the
deployment's own egress address is not derived anywhere in this repository, so
an allowlist would introduce a new host-manifest field whose value is a fact
about somebody's network rather than about this project. The credential
mechanism already exists, is already rotated, and is already proved.

**One host-scoped store, series separated by a `project` label.** Rejected, and
this is the one that would have been cheapest. It halves the memory and gives
one place to query. It is also the single process in the deployment where
`alpha-dev` and `beta-dev` coexist, which makes isolation a labelling convention
maintained by whoever writes the next scrape config. Session 12 proved isolation
across 179 leaves with zero project-scoped values shared; a shared store would
be the first exception, introduced for convenience.

**Serving the store's query API at the edge instead of an exposition
endpoint.** Rejected: it publishes a query language and an admin surface where a
read of telemetry was wanted, and it makes the route's contract the store's
version rather than a format.
