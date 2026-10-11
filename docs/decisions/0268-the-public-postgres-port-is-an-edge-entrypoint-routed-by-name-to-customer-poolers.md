# 0268 — The public Postgres port is an edge entrypoint, routed by name to customer poolers

- **Status:** Accepted
- **Date:** 2026-10-11
- **Session:** 39, Run 1 (`docs/plans/session-39-implementation-plan.md`,
  D2325–D2328, D2335–D2339, D2344, D2349–D2351, D2356, D2357)
- **Affects:** `infra/edge/traefik.yaml` (the `postgres` entrypoint, Run 4),
  `infra/edge/compose.yaml` (`5432:8432`, Run 4),
  `infra/edge/dynamic/baseline.yaml` (the `postgres` TLS option, Run 4),
  `infra/host/docker-user-rules.v4|.v6` and `bin/provision-host.sh` (5432
  admitted, Run 4), `bin/deploy-project.py` (`require_edge_serves_this_release`
  requires the entrypoint, Run 4), `compose.yaml` (`customer-pool`,
  `customer-direct` under `profiles: [public-endpoints]`, Run 5),
  `src/agentic_postgres/runtime_override.py` (their label TCP routers, Run 5),
  `src/agentic_postgres/naming.py` (`endpoint_hosts`, Run 3),
  `schemas/project.schema.json` (manifest 11, `database.public_endpoints`,
  Run 3), `schemas/outputs.schema.json` (outputs 22, `database.public`, Run 3),
  `bin/project-runtime.sh` (the `public-endpoints` profile, Run 5),
  `projects/control/migrations/templates/0005-control-endpoints.sql` and
  `GET /v1/projects/{key}/connections` (Run 6), every publication guard
  (Run 4). Requirements `EP-EDGE-001`, `EP-ROUTE-001`, `EP-DOC-001`,
  `EP-POOL-001`, `EP-API-001`, `EP-SNIP-001`, `EP-LIVE-001..003`.
- **Amends:** ADR 0246 item 2 — *"one Postgres port whose shape Session 39
  measures and records in its own ADR"*: the port is **5432**, the edge's.
- **Supersedes, for the edge only:** what was left of ADR 0044's *"there is no
  publication"* (ADR 0246 already lapsed its standing). **A project still
  publishes nothing**: `runtime_override.publication()` keeps raising,
  `compose.yaml` keeps zero `ports:` keys, and its two tests stay byte-identical.
- **Related:** ADR 0013 (routes are labels), ADR 0085 (no file-provider router
  for a tenant), ADR 0002 (names are derived once), ADR 0244 (the edge's
  bounds; its one recreation), ADR 0040 (`pooled_public` and CFG-010 refused —
  kept), ADR 0269 (who may pass the door), ADR 0158 (the deployed document is
  the address book).

## Context

Stage 5 sells a project a customer connects to from their own machine. ADR
0044 rejected *"publish through Traefik's TCP router with SNI"* for Session 4
and recorded it as *"the direction any future public pooler would have to
take"*. ADR 0246 item 2 admitted one Postgres port and left its shape to this
session's measurement. The stage plan (D1958) asked five questions: can the
edge route the Postgres protocol by SNI and terminate TLS for libpq's two
negotiations; is a wrong name refused; which hostnames; HTTP-01 or DNS-01;
and is wake-on-connect possible.

What stands in the way, read from the tree: `postgres` joins `internal` and
`backup` and its guard refuses `edge`; the platform `pgbouncer` joins
`internal` only; the image's `pg_hba` admits every role from any address by
SCRAM; the file provider must never hold a tenant's router; every guard in the
repository — the edge's tests, the host firewall, ufw, the listener check, the
external scan — says *80 and 443*.

## Measured

Planning (2026-10-10) and Run 1 (2026-10-11), WSL, the pinned images:
Traefik 3.7.10, PgBouncer 1.24.1, `pgvector/pgvector:pg18` (psql 18.4).
Transcripts in WSL `~/s39/run1/rig39/` (`rig39a.txt` … `rig39f.txt`), copied
to the scratchpad.

**The gateway (rig 39a, label routers through the Docker provider with the
managed-scope constraint, the option file exactly as below):**

| Case | Result |
|---|---|
| libpq 18, `sslmode=verify-full`, default negotiation (`SSLRequest`), both names | connected; the backend reads `ssl=false` and Traefik's address |
| `sslnegotiation=direct`, both names | connected |
| **the default TLS options (planning 0a)** | **refused**: *"tlsv1 alert no application protocol"* — libpq 18 offers ALPN `postgresql`, Traefik's default offers `h2`/`http/1.1` |
| wrong SNI (`require`, `verify-full`); no SNI (`sslsni=0`) | refused, *"SSL error: unexpected eof while reading"* |
| `channel_binding=require` | refused: *"server did not offer an authentication method that supports channel binding"* — a terminating proxy cannot offer it |
| plaintext (`sslmode=disable`), entrypoint `readTimeout: 10s` | refused after **11.4 s** (the client's docker start included), *"expected authentication request from server, but received H"*; with the default it was held **61.6 s** (planning 0e) |
| **control for the deadline**: a 75 s query with the client silent, both names | **survived** (76.7 s) — the read deadline governs only the bytes before routing |
| through a published port (`25432:8432`, `hostaddr=127.0.0.1`) | connected |
| the backend container stopped | refused exactly like a wrong SNI (its label router is gone); **control**: started again → connected |
| psql's cancel (Ctrl-C, `timeout -s INT 3`) through the gateway | **did not cancel**: psql printed *"Cancel request sent"* and the 30 s statement ran to the end (31.6 s); **control** without the gateway: cancelled in 4.4 s |

**The certificate (rig 39b, Pebble + `pebble-challtestsrv` pinned by digest in
the rig, the edge's resolver shape `httpChallenge.entryPoint: web`):** two TCP
routers naming `tls.certresolver` and `tls.domains[0] = {main: pool.a.test,
sans: [direct.a.test]}` produced **one** certificate naming both hosts (Traefik
logged *"Trying to challenge certificate for domain [pool.a.test
direct.a.test] found in HostSNI rule"*), issued in ~6 s, served on both SNIs
with ALPN `postgresql` negotiated (`openssl s_client -starttls postgres`).
**Control**: an HTTP router with the same resolver issued too. The fallback
(an HTTP router holding the resolver) was not needed.

**The drivers (rig 39c/39c2, the four fixture images built from
`services/clients/*` unchanged, the rig's CA):** psql (control), node-pg 8.16.3
(`ssl: {ca}`) pooled and direct, psycopg 3.2.12 (libpq 17.6, `verify-full`)
pooled with server-side prepared statements, Prisma 6.19.1 Client pooled and
`prisma migrate deploy` direct — **all connected** through the gateway; so each
sends SNI and none is refused for ALPN. Prisma's Client sends `search_path` as a
startup parameter whenever the URL names `schema=`, and PgBouncer refused it —
*"unsupported startup parameter: search_path"* — until the pooler carried
`track_extra_parameters = search_path`; then it passed, and a `schema=` naming
a schema the role cannot use was refused by the grants (`42501`), not by the
door. `migrate deploy` sends no such parameter. **Prisma needs no
`pgbouncer=true`** with `max_prepared_statements = 100` (six writes, four
parallel reads). psycopg's **`cancel_safe()`** (libpq ≥ 17's encrypted cancel,
which repeats the TLS negotiation and so carries SNI) **cancelled through the
gateway in 3.0 s**; its legacy `cancel()` did not.

## Decision

1. **The gateway is the existing edge.** A fifth entrypoint:

   ```yaml
   postgres:
     address: ":8432"
     transport:
       respondingTimeouts:
         readTimeout: 10s
   ```

   published `"5432:8432"` beside 80 and 443 (unprivileged in the container,
   like `web` and `websecure`), and a TLS option in `baseline.yaml`:

   ```yaml
   postgres:
     minVersion: VersionTLS12
     sniStrict: true
     alpnProtocols:
       - postgresql
   ```

   Every TCP router names `tls.options: postgres@file`. **No product-owned TCP
   proxy is built.** A project deploy refuses an edge whose static config lacks
   the entrypoint (`require_edge_serves_this_release`, D811's precedent); the
   edge is recreated once, announced (Sheet E1).
2. **Routes are labels on two new services, never file-provider routers and
   never to the database or the platform pooler.** `customer-pool` and
   `customer-direct` (ADR 0269 says who may pass them) join `edge` and
   `internal`; each carries `traefik.tcp.routers.<derived>.rule=HostSNI(...)`,
   `tls.options=postgres@file`, `apg.traefik.scope=managed` and
   `traefik.docker.network=${EDGE_NETWORK_NAME}`, its service port 6432.
   `postgres` and `pgbouncer` keep their networks and their guards unchanged.
3. **Hostnames derive from the project's one declared domain**:
   `naming.endpoint_hosts(domain) -> (pool.<domain>, direct.<domain>)`; one host
   port, 5432, carries both.
4. **One certificate per project by the edge's existing HTTP-01 resolver**
   (the operator, 2026-10-10): `customer-pool`'s router carries
   `tls.certresolver` and `tls.domains[0] = {main: pool.<domain>, sans:
   [direct.<domain>]}`, `customer-direct`'s names the same; Traefik stores one
   certificate. **Two more grey A records per slot, by hand**, because the
   proxied wildcard answers every name below the zone with Cloudflare's
   addresses; `slot.observe` reads all three before `ready`. No DNS-edit
   credential on the host.
5. **The facility is per project and only a slot has it.** Manifest schema 11
   `database.public_endpoints: {enabled: boolean}` (default `false`, absent
   below 11, migratable); `slot.slot_manifest` writes `true`; alpha and beta
   stay off; **a manifest that enables both `control` and `public_endpoints` is
   refused**. The services carry `profiles: [public-endpoints]`, selected by
   `project-runtime.sh` iff the rendered `compose.env` says
   `APG_PUBLIC_ENDPOINTS=1` — a facility profile, beside the session profiles
   that say *when* (`mirror` the nearest precedent). `pooled_public` and CFG-010
   are untouched: the platform pooler is never public.
6. **The address book.** Outputs schema 22 gains `database.public` =
   `{enabled, pooled: {host, port, user, database, sslmode}, direct: {…}}`,
   `sslmode` `"verify-full"`, **no URL and no password**; `null` members when
   disabled. `database.pooled`/`direct` keep their loopback meaning. The
   control set's `0005` records it in `app.control_projects.endpoints` from the
   deployed document; `GET /v1/projects/{key}/connections` serves it with
   snippets, `409 not_available` when it is null. Snippets exist only for the
   clients measured above, the password always a placeholder; Prisma's names
   no `pgbouncer=true`.
7. **The customer poolers carry `track_extra_parameters = search_path`** —
   Prisma's Client is refused without it, and the setting only lets a client's
   own `search_path` reach its own server connection; the grants decide what
   it can touch.
8. **Every guard moves in one run to the measured set `{80, 443, 5432}`**
   (Run 4): the edge's tests, `test_only_traefik_publishes_host_ports`, the host
   firewall v4/v6, ufw, the listener check, `test_listeners.py`,
   `test_host_infrastructure.py`, `test_session2_host.py`, external
   `FORBIDDEN_PORTS` (loses 5432 only), `test_session4_public_transports.py`'s
   5432 assertion replaced in the same commit by EP-LIVE-002's stricter one.
   6432, the loopback range, 8080, 8443, 9000, 2375/6 and 5433 stay forbidden.
   Widening an allowlist to a measured set, not weakening it.
9. **Wake-on-connect is not built.** A stopped container's label router is
   gone, so a sleeping project's names refuse like a wrong name; Traefik has no
   hold-and-wake for TCP and building one is the proxy decision 1 avoids.
   `wake_on_connect` stays `planned`.

## Consequences

- **Postgres sees the gateway's address**: no per-client address rule exists
  and a customer cannot allowlist addresses.
- **Channel binding is not offered** through a terminating gateway.
- **A plaintext peer holds a socket for ~10 s** before Traefik answers it.
- **A cancel request crosses the gateway only when the client encrypts it**:
  libpq ≥ 17's `PQcancelCreate` family (psycopg's `cancel_safe()`) does;
  psql's Ctrl-C and psycopg's legacy `cancel()` send a plaintext
  CancelRequest with no name, which no router can match. psql reports *"Cancel
  request sent"* regardless. `statement_timeout` is the bound for the rest; the
  Ledger's Connect text says so.
- The edge carries one more port, so every edge change still pays the shared
  recreation (Session 35's 24.4 s, re-measured on OVH at Sheet E1).
- Let's Encrypt is charged one issuance per enabled project, against 50 per
  registered domain per week.
