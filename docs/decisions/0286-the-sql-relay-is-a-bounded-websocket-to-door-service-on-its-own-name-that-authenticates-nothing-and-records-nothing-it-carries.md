# 0286 — The SQL relay: a bounded WebSocket-to-door service on its own name that authenticates nothing, holds nothing, reaches only door names through the edge, and records none of what it carries

- **Status:** Accepted
- **Date:** 2026-10-21
- **Session:** 44, Run 1 (`docs/plans/session-44-implementation-plan.md`,
  D2733, D2736, D2739–D2743, D2751, D2759–D2764, D2769; rigs 44a, 44c, 44d;
  Sheet D0)
- **Affects:** `services/sql-relay/` (new image: `Dockerfile`, `relay.py`),
  `versions.in.yaml` and `versions.env` (`WEBSOCKETS_VERSION`), `compose.yaml`
  (service `sql-relay`, profile `sql-relay`), `bin/project-runtime.sh` (adds
  the profile when the render says so), `src/agentic_postgres/naming.py`
  (`sql_relay_host`, `sql_relay_origin`, `sql_relay_zone`, the door grammar),
  `src/agentic_postgres/rendering.py` and `runtime_override.py` (the relay's
  environment and router, the control project only), `src/agentic_postgres/config.py`
  (its limits), the Cloudflare zone (one grey `A` record). Requirements
  `SQL-RELAY-001`, `SQL-RELAY-002`, `SQL-RELAY-003`, `SQL-PLANE-001`,
  `SQL-HOST-001`, `SQL-LIVE-002`.
- **Related:** ADR 0070 (the connection budget), ADR 0085 (label routers),
  ADR 0167 (the edge's alias on every project network), ADR 0195, ADR 0244
  (every service bounded), ADR 0246, ADR 0268 (the public Postgres door — read
  whole), ADR 0269 (the customer roles' limits), ADR 0280 (the facility profile
  shape), ADR 0281 (the console's cookies), ADR 0285 (the editor).

## Context

The editor (ADR 0285) speaks PostgreSQL's protocol from a browser, which can
open a WebSocket and nothing else. Something must turn a WebSocket into a TCP
connection to a project's door. The door is already public (5432, ADR 0268):
anyone can open what such a service could open, so it needs no identity — what
it must not become is a way to reach anything else, a free pool of sockets, or
a recorder. Nothing in the tree had ever carried a WebSocket
(`mcp_origin.py:59`). The console's cookies are `__Host-…; Path=/` (ADR 0281),
so a WebSocket to a path on the console's own host would carry them; **the
operator chose on 2026-10-21 (D2733) that the relay has its own name.**

## Measured

- **Rig 44d** (2026-10-21, `~/s44/rigs/44d/`): `websockets` **17.2**
  (2026-10-03, the newest release at least 14 days old; 17.3 was 2 days old),
  `License-Expression: BSD-3-Clause`, **`requires_dist` empty** (`pip show`:
  `Requires:` nothing), `requires_python >=3.11`; the
  `cp312-manylinux…x86_64` wheel `sha256:6627b913b8586b1c06db9516b31dd0dfbc621de3bb9312616d92a7e44f268a5b`,
  the sdist `sha256:36c2fb94c990cc2545143b12690e2de6c16300f9dbe5b4f33fa300cf57dc8792`.
  In `PYTHON_RUNTIME_IMAGE` with `serve(…, origins=["https://a.test"],
  max_size=1<<20, process_request=…)`: `Origin: https://b.test` → **`403`**,
  never `101` (the control, `https://a.test` → `101`); **no `Origin` → `403`**;
  a 2 MiB message → close **`1009`** (the control, 1 MiB, echoed). **Two
  readings the design follows (D2762)**: `process_request` runs **before** the
  `origins` check (a bad path with a foreign `Origin` → `400`), and the library
  **logs a handler's traceback on its own logger** (`websockets.server`,
  *"connection handler failed"*). **Re-read on 17.1 in Run 2** (D2771:
  2026-08-26, BSD-3-Clause, no `requires_dist`, wheel
  `sha256:0c863507ada5805517ca6dff1c524dcd42942efe6304dacf06700878398d21a6`,
  sdist `sha256:acfea4c20bf54384883ea33b1240fc1db4f52e190823a4e2b334bc3e8bfca96a`):
  every reading identical.
- **Rig 44a** (`~/s44/rigs/44a.txt`): Traefik **3.7.10** (`TRAEFIK_IMAGE`) with
  `websecure`'s production `respondingTimeouts` (read 30 s, write 30 s, idle
  60 s) and the baseline rate limit, Chromium from the pinned Playwright image:
  1. A page on `console.test` holding `__Host-c` opened
     `wss://relay.test/…`: the relay saw `Origin: https://console.test` and
     **no `Cookie`**. The control, a WebSocket to `wss://console.test/…`,
     carried `__Host-c=1`.
  2. A WebSocket to a host the policy does not name: blocked by `connect-src`,
     **no request at the edge**.
  3. 65,792 binary bytes round-tripped exactly.
  4. **Every 150-second session survived**: idle with no pings, idle with
     20-second pings, the server streaming one frame a second, the client
     sending one a second — **Traefik applies none of `websecure`'s timeouts to
     an upgraded connection** (D2763). D2751's stop does not fire.
  5. 500 frames over 5 s on one socket: all echoed, the socket open; the
     control, 100 plain `GET`s at once from the same page: 43 × `200`,
     57 × `429` — **the rate limit counts the upgrade, not the frames**.
  6. A client sending `X-Forwarded-For: 203.0.113.9` and `X-Real-Ip:
     198.51.100.7`: the relay saw **both replaced by the true peer** (the
     control, no client headers: the same values) — the edge **overwrites**
     them (D2764), so `X-Real-Ip` can key a per-source ceiling.
  7. 32 sessions each streaming 1 KiB ten times a second for 60 s (19.4 MB
     delivered, no error): the rig relay's `memory.current` peaked at **19.5 MiB**
     and `pids.current` at **3**; the control, 0 sessions, 18.8 MiB and 3. The
     workstation's reading, not the host's.
  8. An upgraded session is one access-log line with `DownstreamStatus: 0`.
- **Rig 44c** (`~/s44/rigs/44c.txt`): in `PYTHON_RUNTIME_IMAGE`,
  `/etc/ssl/certs/ca-certificates.crt` is present and
  `ssl.create_default_context()` loads it. SSLRequest, `S`, then TLS with
  `server_hostname=<name>` and ALPN `postgresql` against a rig Traefik door:
  verified with the rig CA added (TLSv1.3, ALPN `postgresql`); **the control**,
  the image's store alone → `unable to get local issuer certificate`; SNI
  `unknown.test` → EOF in the handshake → `4502`. A TCP router whose backend
  does not resolve also answers no TLS (EOF), the same refusal. **Then the live
  door, read-only, with the image's own store**: `pool.slot3.agenticpostgresql.com`
  and `direct.slot3…` **VERIFIED**, TLSv1.3, ALPN `postgresql`, one certificate
  `CN=pool.slot3.agenticpostgresql.com`; `pool.slot99.agenticpostgresql.com` →
  EOF → `4502`.
- **Sheet D0** (2026-10-21 18:14Z, the agent through the Cloudflare API): the
  zone held 33 records and none named `sql` (D2759); one `A` record
  `sql.agenticpostgresql.com` → `15.204.231.45`, **`proxied: false`**, TTL auto,
  comment *"apg sql relay (Session 44, D2733)"*, id
  `af246339104e95bba082ecfbc7f510ae`, read back; 34 records, the two Pages
  CNAMEs still the only proxied ones; `nslookup … 1.1.1.1` →
  `15.204.231.45`. With no router yet, the edge answers the name on 443 with a
  TLS alert `unrecognized_name` (112), not a 404 (D2760).

## Decision

1. **Its own name, derived once.** `naming.sql_relay_host(control_domain)` =
   `"sql." + <the control domain without its first label>` (refused when the
   remainder has fewer than two labels): `control.agenticpostgresql.com` →
   `sql.agenticpostgresql.com`; `naming.sql_relay_origin(host)` =
   `wss://<host>`; `naming.sql_relay_zone(control_domain)` = the control domain
   without its first label. Rendered for the control project only. The name is
   one grey `A` record (Sheet D0); its certificate comes from the edge's
   existing resolver when the relay's router first appears — one issuance,
   never retried in a loop.
2. **A new image, `services/sql-relay/`**, from `PYTHON_BASE_IMAGE`, installing
   **`websockets` pinned** — **17.1**, the version the dev lock already holds,
   so the image and the offline suite run one version (D2771) — as
   `WEBSOCKETS_VERSION` (`registry: pypi` in
   `versions.in.yaml`, written to `versions.env` by `bin/lock-versions.sh
   --update --packages-only`) with an import self-check — the auth image's
   `segno` pattern. A compose service **`sql-relay` under the facility profile
   `sql-relay`**, added by `bin/project-runtime.sh` only for the control
   project (the `console` shape); `read_only`, uid 65532, every capability
   dropped, network `edge` only, **no secret, no mount, no `env_file`, no port**;
   bounded by ADR 0244's rule from its measured peaks (Run 3). One router,
   ``Host(`sql.<zone>`)`` on `websecure`, the baseline chain.
3. **Admission, in this order, all inside `process_request`, before any TCP**
   (D2762 — the library's own `origins` check would run after the path's):
   (a) **`Origin` equal to the console's origin byte for byte**
   (`APG_SQL_RELAY_ALLOWED_ORIGIN` = `naming.console_origin`), else **HTTP
   `403`**; (b) **the one path**, `GET /v1/door/<host>`, with `<host>`
   fullmatching
   `^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)?(?:pool|direct)\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.<zone>$`
   (the zone escaped, `APG_SQL_RELAY_ZONE`), length ≤ 253, no query, else
   **HTTP `400`**; (c) **the ceilings** — 32 sessions in total, 4 per door
   host, 4 per source address read from `X-Real-Ip` (D2764) — else the upgrade
   is completed and closed **`4429`**, so the page can say why.
4. **One upstream, rendered, never typed** (D2739): `APG_SQL_RELAY_UPSTREAM` =
   `apg-edge-proxy:8432`, from `host_config.EDGE_PROXY_ALIAS` and the postgres
   entrypoint's port. The only name the relay resolves is that alias, through
   Docker's resolver; **the door name is used only as SNI**, never looked up.
   It sends SSLRequest, requires `S`, then TLS ≥ 1.2 with **SNI = the door
   name, ALPN `postgresql`, `CERT_REQUIRED` and the hostname checked against
   the image's system trust store**. Any failure there — a refusal, EOF, a
   verify failure, a timeout of 10 s — closes **`4502` *"could not reach the
   database"***, never *asleep* (ADR 0195; ADR 0268 `:68,73`). The edge's
   `sniStrict` routing is the only router.
5. **The bounds, each one constant in `relay.py`** (D2741): idle **300 s** (no
   frame either way) and total **1,800 s** → `4408`; one message ≤ **1 MiB**
   (`max_size`) → `1009`; **64 MiB** towards the browser per session → `4413`;
   **64 KiB** from the browser before the door is ready → `4413`; a text frame
   → `4400` (the protocol is bytes). **Pings every 20 s**, for whatever lies
   between the browser and the edge — not for Traefik, which times out no
   upgraded connection (D2763), so the relay's own idle limit is the only one.
   **The close codes are `4400 4408 4413 4429 4502`**; an `Origin` or path
   refusal is an HTTP status before the upgrade, so no close code exists for
   it (D2769: the plan's `4403` is dropped — it could never be sent).
6. **One line per session on stdout, and nothing else** (D2743):
   `apg-sql-relay session=<16 hex> door=<host> outcome=<closed|refused|unreachable> code=<n> seconds=<n> up=<bytes> down=<bytes>`;
   a refusal before the upgrade is `apg-sql-relay refused reason=<origin|path>`
   with **no `Origin` value and no path**; a ceiling's refusal is a session line
   with `outcome=refused code=4429`. No
   frame, statement, row, SASL message, header or exception text. **The
   library's loggers are silenced** (D2762): `websockets` gets a handler that
   writes nothing, and the relay catches every exception in a session itself.
   A canary proves it offline (a known password and a marker through the relay,
   every line read) and live (the editor walk's marker read absent from the
   relay container's whole log).
7. **The relay adds no claimant to ADR 0070's budget** (D2736): an editor
   session is one client of an existing door, counted against the role's
   `CONNECTION LIMIT` by PostgreSQL and PgBouncer exactly as `psql` is.
   `max_connections` and the budget do not move.

## Alternatives

- **A path on the console's own host** (`/console/sql`): every handshake would
  carry the console's session cookies, which the relay would have to ignore.
  Rejected by the operator (D2733).
- **A relay per project**: a service in every slot for a feature used from one
  console; the door is already per project.
- **A relay that checks the console's session**: it would hold a verification
  key and receive a token, and it would still reach nothing the public door
  does not answer anyway. Holding nothing is the stronger property.
- **Traefik alone**: it carries a WebSocket or a TCP stream, never one into the
  other.
- **RFC 6455 written here**: ~250 lines of parser in front of the internet; a
  maintained library with no dependency and a one-line pin is the smaller risk.

## Consequences

- A third public surface on the host's 443 and the first long-lived HTTP
  connection the edge carries; its outage is the editor's, never the doors'.
  It is charged at its ceilings, like every non-database service.
- **The relay can read every editor session** (the operator's choice). A change
  to its logging is a security change; the live canary runs at every trip.
- 32 sessions can be held by anyone for up to 30 minutes each.
- `sql.agenticpostgresql.com` is one more Let's Encrypt name, renewed by the
  edge like the others.
