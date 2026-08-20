# 0128 — The agent plane publishes one path, and its health is private by absence

Status: accepted
Date: 2026-08-20
Session: 8, Run 7
Affects: ADR 0013, ADR 0108, ADR 0109, ADR 0121, ADR 0124, D162, D186, D187,
D231, D353, D408, D441, D442, D443,
`src/agentic_postgres/runtime_override.py`, `src/agentic_postgres/naming.py`,
`services/auth-api/app/mcp_runtime.py`, `services/auth-api/app/mcp_health.py`

## Context

Run 7 publishes the agent plane. The plan asks for four things: ADR 0108's
frozen route form with derived precedence, a `/mcpx` boundary proved by which
service answered, **Host/Origin protection**, and a **private unauthenticated
health** surface whose readiness invents no private dependency endpoint.

Three of those turn out to be decisions rather than settings, because the pinned
framework does not provide what the runbook assumed.

## What was measured

Against **fastmcp 3.4.0** — ADR 0121's measured ceiling, since 3.4.1 cannot share
a process with this repository's FastAPI.

**Host and Origin protection are not available at this pin.**

```
http_app parameters: path, middleware, json_response, stateless_http,
                     transport, event_store, retry_interval
  host_origin_protection   ABSENT
  allowed_hosts            ABSENT
  allowed_origins          ABSENT
```

They exist at 3.4.7. Adopting that version would mean bumping FastAPI to 0.141.1
inside a run about publishing, which ADR 0121 refused for D321's reason.

**And the runtime does nothing about either today**, which is the half that
matters:

| request | result |
|---|---|
| `Origin: https://evil.test`, valid token | **200**, and no `Access-Control-Allow-Origin` in the reply |
| `Host: evil.test`, valid token | **200** |
| `OPTIONS /mcp` with an `Origin` | **405**, no CORS headers |
| CONTROL — no token | **401** |
| CONTROL — good token | 200 |

So a cross-origin request is *processed*; a browser simply cannot read the
answer. The 405 on preflight is what stops a browser sending a JSON POST at all,
and it is the absence of a CORS middleware rather than anything the runtime does.

**Custom routes mount at the application root and are not behind the verifier.**

```
route table:  /mcp   /health/live   /health/ready
GET /health/live       -> 200   (no token)
GET /health/ready      -> 200   (no token)
GET /mcp/health/live   -> 404
POST /mcp (no token)   -> 401   <- the control: auth is still on
```

That last pair is the load-bearing one. The health routes are open **and** the
MCP surface still refuses an unauthenticated caller, so "health answered" cannot
be read as "authentication is off".

## Decision

**1. The router publishes exactly one path, in ADR 0108's frozen two-matcher
form, and strips nothing.**

```
Host(`${PROJECT_DOMAIN}`) && (Path(`/mcp`) || PathPrefix(`/mcp/`))
```

`PathPrefix` is a string prefix (D162), so the single-matcher form would answer
`/mcpx`. **No `stripprefix` middleware**, because the application serves `/mcp`
at its own root — measured — so the published path and the served path are the
same string and a strip would produce a 404 at the service.

Precedence is **derived** and no `priority` is set on any router (ADR 0108). No
other rule in this deployment matches `/mcp`; a test asserts that by
interpolating every rule rather than by reasoning about them.

**2. `/mcpx` reaches no backend, and the proof says which.** Unlike the storage
route, `/mcp` is top-level: there is no parent router to catch a sibling, so
`/mcpx` matches nothing and Traefik answers its own 404 — which is
distinguishable from a routed one by a 19-byte body and a missing `RouterName`
(D186, D187, D353). The boundary proof reads that, never the status code.

**3. Health is private by absence of a route, not by a guard.** `/health/live`
and `/health/ready` are served at the application root and **no Traefik router
publishes them**, so nothing outside the internal network can reach them. The
public answer to "is this project up" stays `__apg/healthz`, served by
`edge-probe` (D231).

**Readiness reports only what startup established** — the key set is loaded and
the capability lock is loaded — and calls nothing. Anything else would invent a
private dependency endpoint, and a readiness probe that reaches PostgREST would
take this container out of service for a fault that is not its own.

**4. A request carrying an `Origin` header is refused.** Not an allowlist: **any**
`Origin`. This surface is an agent API and no legitimate client is a browser, so
the header's presence is itself the signal. It is stricter than an allowlist,
needs no configuration, and cannot drift from a manifest field.

**5. Host is Traefik's, and the runtime does not duplicate it.** The router's
`Host()` clause is what decides which requests reach the container, and it is
derived from the project's domain — which `naming.py` owns. A second Host check
inside the image would need the domain as a setting, and that is a second
authority for a value ADR 0002 gives to one place.

## Alternatives rejected

**Bump to 3.4.7 for `host_origin_protection`.** It carries FastAPI 0.141.1 into
the auth service, which ADR 0121 refused with a measurement behind it. The
protection it offers is also the pair this ADR implements: one by refusal, one by
the edge rule that already exists.

**An `allowed_origins` manifest field.** A list nobody would populate, publishing
a browser story this surface does not have. ADR 0109 already says the CORS
middleware instructs a browser and refuses nobody; attaching one here would
advertise a cross-origin flow that is deliberately impossible.

**Strip `/mcp` and serve the MCP endpoint at the service root.** It would make
the published path and the served path differ, and the strip would then be
load-bearing for correctness rather than for tidiness. Measured: the app already
serves `/mcp`, so the no-strip form is the one where the two agree.

**Publish the health routes and protect them with a token.** A readiness probe
that needs a credential is a probe the healthcheck cannot run without one — and
this container is the one runtime in the deployment that deliberately holds no
credential of its own (ADR 0121).

**Reject an unknown `Host` in the runtime too.** Defence in depth is the argument
for it, and the argument against is stronger: the value it would compare against
is the project domain, which arrives as a setting, and the failure mode of a
wrong setting is a container that refuses every request while looking configured.

## Consequences

- **The agent plane's public surface is one path.** Everything else it serves —
  health, and whatever a later session adds at the root — is reachable only from
  inside the internal network.
- **A browser cannot use this API**, by construction and now by refusal. If a
  browser client is ever wanted, this ADR is what has to be revisited, and the
  refusal is a single named check rather than a scattered assumption.
- **`mcp_health.py` becomes ADR 0124's third transport row.** It performs a
  loopback HTTP request from the container's own healthcheck, and the row states
  that, which is what the allowlist is for. Run 4 deferred exactly this (D429)
  rather than weaken the guard; the guard now has a mechanism for it.
- The runtime's Origin refusal and the edge's Host rule are recorded in different
  places on purpose, because they are enforced in different places.
