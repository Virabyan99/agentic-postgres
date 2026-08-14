# 0085 — A route lives with its backend, and that is the cheaper failure

Status: accepted
Date: 2026-08-14
Session: 6, Run 10
Affects: D186, D202, D208, D229, `runtime_override.py`, `edge_credentials.py`

## Context

D208 has been `pending` since Session 5 Run 7. It recorded a measured fact and
left the design question open:

> Whether the three remaining middlewares move to the file provider is a
> decision with a real trade-off and belongs to whoever takes it: the route
> would answer **502** instead of 404 while its backend is down, which is
> unambiguous where a 404 is not, at the cost of three more generated files per
> project.

Session 6's plan closed that question in a sentence — *"Middlewares go in
Traefik's file provider — which closes D202/D208 rather than deferring them a
third time"* — and this run measured the sentence before implementing it.

### The rig

One Traefik at the locked digest
(`traefik:v3.7@sha256:9c3b91d5…dcb2ac`), the docker provider constrained on
``Label(`apg.traefik.scope`,`managed`)`` exactly as `infra/edge/traefik.yaml`
constrains it, and one upstream container carrying three routers:

| Route | Router defined by | Middleware defined by |
|---|---|---|
| `/lbl` | a container label | a container label, on the same container |
| `/filem` | a container label | **the file provider**, referenced `@file` |
| `/fileroute` | **the file provider** | the file provider |

**Control**, before anything was taken away: all three answered 200, and the
two stripped routes delivered `/` and `/x` to the upstream while the unstripped
`/api/app` delivered `/api/app` — so the rig can tell a route that works from
one that does not, and a strip that happened from one that did not.

### 1. Moving a middleware buys nothing

With the backend container stopped:

    /lbl         404 19 bytes   404 page not found
    /filem       404 19 bytes   404 page not found
    /fileroute   502 11 bytes   Bad Gateway

`/filem`'s middleware lives in the file provider and survived. Its **router**
does not: a router defined by a container label is withdrawn when the container
goes, so the route is gone whatever its middleware is doing. The access log
settles it — the 502 is logged with `"RouterName":"fileroute@file"` and the two
404s are logged with no router at all, which is Traefik's own 404 and is
byte-identical to the answer an unrouted hostname gets (measured: 19 bytes for
`Host: nothing.test`).

**So the plan's sentence is wrong about D208.** Moving the three remaining
middlewares into the file provider would have produced three more generated
files per project and changed no observable behaviour.

### 2. And moving the router breaks project isolation

The 502 is the outcome D208 wanted, and reaching it means moving the **router
and its service** into the file provider. A file-provider service names its
backend by URL, so it can only address a container by DNS — and on a Docker
network the name is the **Compose service name**, which every project shares.

Measured, with the edge attached to two project networks as the real one is,
and two backends both aliased `shared`:

    control — a name on one network only
      upstream-a  ->  172.20.0.2      (project A)
      upstream-b  ->  172.21.0.2      (project B)

    the shared Compose service name, ten resolutions
      10  ->  172.20.0.2              (project A, every time)

Project B is not reachable by that name at all. A router in the file provider
serving project B would have sent project B's requests to **project A's
container**, deterministically, with no error anywhere. That is `DEP-ISO-003`
broken by a routing table.

The docker provider has no such problem because it does not resolve a name: it
reads the container's own address off the container it found the labels on.

## Decision

**Routers, services and their middlewares stay on container labels.** The
credential middleware stays in the file provider, for the reason it was put
there and no longer for the reason D208 gave: a `usersFile`, and now an inline
`users` list (ADR 0086), cannot be expressed as a label at all.

D208's trade-off is answered rather than deferred: the 502 is genuinely more
legible than the 404, and it is not purchasable at this price. **A route that
disappears with its backend is the cheaper failure**, because the alternative is
a route that stays up and points at another tenant.

The consequence is written down where it is felt rather than left implicit:
`assert_api_converged` already polls both routes rather than checking one after
spending the window on the other (D208's harness fix), and a 404 during a
deploy is diagnosed from the access log — `RouterName` present or absent —
before anything is concluded.

## Alternatives

**Move the routers and services to the file provider and address backends by
container name.** `naming.derive` already predicts Compose's container name
(`apg-<key>-postgres-1`) and it is per-project, so the ambiguity above would go
away. Refused: that name is a *prediction* the model deliberately does not
enforce with `container_name:` (D55), and it is checked against reality on the
host rather than relied upon. Routing every request through a predicted name
would make the whole edge plane depend on Compose's naming convention not
changing — and the failure, again, is a route pointing at the wrong project
rather than a route that is absent.

**Give each project's backend a per-project network alias.** This works and is
the honest version of the alternative above. It is refused for this run because
it adds a second identity for every routed container, derived in a second place,
to buy a better status code for a container that is down — and ADR 0002 exists
to stop exactly that trade being made casually. It is the move to reach for if a
future session has a reason to want file-provider routers.

**Leave D208 pending a third time.** Refused. The question was answerable in one
rig and the answer changes what a reader believes about the design.

## Consequences

- Three middlewares that were going to move do not, and the reason is measured
  rather than aesthetic.
- `/api/app` is bounded by the same ``Path(`x`) || PathPrefix(`x/`)`` pair
  every other route uses, re-measured for this route: `/api/application`,
  `/api/app-extra`, `/api/app2` and `/api` all 404 while `/api/app` and
  `/api/app/x` serve.
- **A route is unavailable while its backend is restarting, by design.** Any
  proof that touches a route across a restart polls it; a single check after a
  restart measures the window rather than the property.
- D202 is closed separately and was already closed in substance: ADR 0069 moved
  "loads nothing from the internet" from a third party's default to a CSP this
  repository serves, which is what D202 asked for.
