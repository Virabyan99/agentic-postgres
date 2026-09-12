# 0205 — Studio is a same-origin forwarder that holds the human's token and binds loopback with no alternative

- **Status:** accepted
- **Date:** 2026-09-12
- **Session:** 24, Run 1 (D1243, D1245, D1246, D1249, D1250, D1252, D1253,
  D1254, D1256, D1259–D1262)
- **Related:** ADR 0002 (an identity is derived once), ADR 0050 (a reviewed
  surface is checked against what is served, with the expected address
  supplied rather than read out of the answer), ADR 0065/0066 (a rig is a
  second configuration of the product and must be tied to it), ADR 0069 (the
  documentation page's CSP is ours, and that is why the server is
  first-party), ADR 0093 (an operator command imports only what the host
  has), ADR 0097 (what a refusal may say), ADR 0117 (`token_use` is the
  discriminator), ADR 0135 (the audit record is written as the caller), ADR
  0139 (a refusal is translated, never relayed), ADR 0140 (hiding a control is
  not a boundary), ADR 0141/0178 (a denial is audited and names its boundary),
  ADR 0142 (`admin_audit:read` is the one read path), ADR 0158 (the deployed
  document is the address book, not the diagnosis), ADR 0170 (each project
  publishes exactly one verification key), ADR 0171 (the session plane), ADR
  0175 (a released function keeps its arity), ADR 0195 (three outcomes, the
  third reported), ADR 0203 (the dev environment is the database), ADR 0204 (a
  generated client is a claim about the surface it was generated from);
  D105 (a credential reaches a process through its environment or a `0600`
  file and never an argument), D433 (never relay an upstream status), D694 (a
  refusal with a switch is a decision deferred), D1114 (a proof calls the
  product's own command), D1172 (Docker's loopback publication, measured),
  D1210 (the operator set is the capability schema's), D1229 (the residue
  check and the bare-hostname clause).

## Context

There is no Studio. A human who wants to see their rows types `bin/api.sh`
operations under a token `dev-token.sh` minted for root, or reads the Scalar
page at the documentation route behind a Basic password materialised for
Traefik and handed to nobody. A human who wants to see what an agent did calls
`GET /admin/audit` and reads JSON — and what that endpoint returns does not
include the boundary that refused, which is the defect a viewer finds because
a viewer is the first reader that shows a whole row to a person.

The stage plan asks for "a local web UI bound to `127.0.0.1` only … holding
nothing but the human's short-lived token". Every hard question in this
session is inside that sentence, and only one of them is about a UI.

**Where the token lives is the design.** A page that held the bearer — in
JavaScript memory, in `localStorage`, in a query string — is one cross-site
scripting bug or one shared screenshot away from a credential leak. Worse, it
puts a third party's default in the security path: a page on `127.0.0.1`
calling `https://beta-db.example` is making cross-origin requests, so whether
they are permitted is decided by CORS — by what the upstream sends, not by
what this product checks.

**Nothing in the tree serves a page to a human on a workstation.**
`services/docs/serve.py` is the one first-party HTTP server this repository
has: `http.server` plus a fixed path table, our own Content-Security-Policy,
no path joining and no directory walk. It runs in a container on the edge
network. Studio is not that: a container publishes through Docker's proxy and
would make the human's token cross a container boundary for nothing.

### What was measured, 2026-09-12, three rigs with controls

**Rig 24a — the loopback server and its refusals.** `ThreadingHTTPServer`
bound to `("127.0.0.1", 0)` listens on `127.0.0.1:34273`; the CONTROL, the
same class bound to `("0.0.0.0", 0)`, listens on `0.0.0.0:39573` — read from
`ss -ltn`, and read a second way because a test may not have `ss`: connecting
to this host's own interface address reaches the control (`connected`) and is
refused by the loopback server (`ConnectionRefusedError`), while `127.0.0.1`
reaches it. `socket.gethostbyname_ex(gethostname())` offers only `127.0.1.1`
on this machine, so the interface address is read from the interface.

`http.server` exposes `Host`, `Origin` and `Cookie` to the handler exactly as
sent, and every refusal below was answered **before the request body was
read**. Nine arms, each with its passing control, all as expected:

| request | answer |
|---|---|
| `GET /` with no launch cookie | 401 |
| `GET /open/<key>` | 303, `Set-Cookie: apg_studio=…; HttpOnly; SameSite=Strict; Path=/` |
| `GET /` with the cookie | 200 |
| `GET /` with `Host: evil.example:PORT` | 421 |
| `GET /` with `Origin: http://attacker.example` | 403 |
| `GET /` with `Origin: http://127.0.0.1:PORT` | 200 |
| `OPTIONS /__apg/x` | 405 |
| `POST /__apg/x` without `X-Apg-Studio` | 403 |
| `POST /__apg/x` with it | 200 |

A refused `POST` announcing `Content-Length: 1000000` with one byte sent is
answered 403 with `Connection: close` and does not hang the client — which is
what makes "refuse before reading the body" a shape rather than a hope.

**Rig 24b — a deployment on loopback.** The `apg dev` cluster (16.4 s), the
**real** auth application on `uvicorn` bound to `127.0.0.1:0` (0.4 s to ready;
`server.servers[0].sockets[0].getsockname()` exists at the pinned uvicorn
0.50.2 and is how the port is read), PostgREST on `compose.yaml`'s own
`postgrest.environment` values verifying **the application's own published
JWKS** through the `@file` form (`PGRST_JWT_SECRET=@/etc/postgrest/jwks.json`,
schema cache loaded in 1.8 s; CONTROL: the HS-secret form `served` uses loads
too, so both are available at the pinned image), and Traefik published with
`-p 127.0.0.1:0:8080`, its port read with `docker port` (D1172's form).

Against that, as a human whose token the application issued from their own
password:

- **The served REST document is exactly the committed snapshot.** `GET /` with
  `Accept: application/openapi+json` → 16035 bytes → normalized →
  `808ac715c09aeebc…`, equal to `projects/example/contracts/postgrest-openapi.canonical.json`
  **byte for byte**, not merely by digest. Rig 23a showed this for a token the
  rig minted; this is the one thing it could not show — the same equality for
  a token the application issued to a human.
- **RLS is PostgreSQL's, not Studio's**: user A sees 2 notes, user B sees 1,
  and A asking for `owner_id=eq.<B>` sees 0.
- **One login is one live session row.** `GET /auth/sessions` after one login
  returns exactly one row, live, with keys `session_id, created_at,
  last_used_at, revoked_at, revoked_reason`. `created_at` has **microsecond**
  resolution: three logins inside 0.68 s produced three distinct values.
- **PostgREST sends no CORS header at all.** `GET /notes` with `Origin:
  http://127.0.0.1:1` answers 200 with `Connection, Content-Length,
  Content-Location, Content-Range, Content-Type, Date, Server` — and no
  `Access-Control-*` of any kind.

**Rig 24c — the audit reader.** On a cluster with all 33 migrations applied,
`auth_list_agent_audit` returns twelve columns and `denial_reason` is not one
of them (`pronargs` 3). Asking the function for the column errors with
`column "denial_reason" does not exist`. `CREATE OR REPLACE` with the widened
`RETURNS TABLE` is refused by PostgreSQL 18.4 — `cannot change return type of
existing function` — so the repair is a DROP and a CREATE. After the DROP the
auth service is answered `permission denied for function
auth_list_agent_audit`, and after the re-issued GRANT it reads both rows: the
`refused` row carries `scope_not_held` and the `served` row carries NULL.
`pronargs` is 3 before and 3 after.

## Decision

**Studio is one standard-library Python process bound to `127.0.0.1:0`, and it
is a same-origin forwarder.** The browser never holds the token.

1. **The process holds the token; the page holds a launch cookie.** The human's
   password comes from a TTY prompt or a `0600` file owned by the caller —
   never an argument, never an environment variable (D105). The process logs in
   through `POST /auth/login`, keeps the access and refresh tokens in memory,
   refreshes when fewer than `STUDIO_REFRESH_BEFORE_SECONDS` remain, and ends
   the session it began at exit. The page gets one `HttpOnly; SameSite=Strict`
   cookie carrying a per-launch key and nothing else. No response body, header
   or asset ever carries the token.

2. **Every upstream request is made by the process, from an enumerated table.**
   `FORWARDER_TABLE` names seven operations and their methods; each maps to
   exactly one upstream request built from validated parts. There is no free
   path, no SQL of any kind, and no `POST`/`PATCH`/`DELETE` to the REST route
   at all — the query builder reads. This is `bin/api.py`'s shape, and the
   reason it is a table rather than a proxy is that a proxy forwards what it is
   given and a table forwards what it was written to forward.

3. **Five checks on every request, in the process, before anything else.**
   `OPTIONS` → 405 (so no cross-origin preflight can succeed); a `Host` other
   than the bound address → 421; an `Origin` that is present and not the page's
   own → 403; a missing or wrong launch cookie → 401; a `/__apg/` call without
   `X-Apg-Studio: 1` → 403. They are ADR 0140's rule applied: the page is not
   trusted to enforce anything, including the revocation confirmation, which
   the process checks against the path's own agent id.

4. **`127.0.0.1` is a constant and there is no flag.** `studio.BIND_ADDRESS`.
   Binding elsewhere would need TLS the edge cannot give a workstation process,
   its own CSP origin, and a threat model for a token-holding process on a LAN.
   A person who wants that edits the source, which is where `dev-token.sh` puts
   the same kind of refusal. A refusal with a switch is a decision deferred to
   whoever finds the switch (D694).

5. **Studio is a HOLDER, not a verifier** (D1246). It sends `Authorization:
   Bearer` and reads status codes; it imports no `jwt`, no `jwks`, no
   `cryptography`. The verifier count stays four (ADR 0170) and this session
   adds no rotation precondition. An upstream refusal is **classified** — `ok`,
   `refused`, `invalid`, `upstream_failed` — and the upstream body is never
   relayed (D433, ADR 0139).

6. **The surface is checked the way `init()` checks it** (ADR 0204), in Python,
   with the capture's own normalizer and no second canonical form. Four
   answers: `ok`, `stale_contract` naming both digests and the regenerate
   command, `unreachable`, `unreadable`. On anything but `ok` the schema and
   query views are refused and the application views — audit, agents, sessions
   — remain, because those are release operations and not project ones.
   **The expected address is supplied, not read out of the answer**: the
   normalizer takes `expected_host` and `expected_base_path` derived from the
   deployed document's `routes.rest.url`, and a document naming another host is
   refused rather than normalized into agreement (ADR 0050, measured).

7. **The deployed document is the address book and `https` is required**, with
   one written-down exception: a route whose host is `127.0.0.1` or `localhost`
   may be `http`, because loopback never leaves the machine — the same reason
   Studio itself is plain HTTP on loopback. Any other `http` route is refused.

8. **Zero third-party code.** Three hand-written files under
   `services/studio/`, no `package.json`, no bundle, no build step, no CDN, no
   font. The CSP is stricter than the documentation page's — `default-src
   'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src
   'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'` — with
   no `'unsafe-inline'`, because nothing here writes styles at runtime. The
   SBOM is the Python standard library and three files.

9. **Nothing is logged but a method, a path without its query, and a status.**
   `http.server`'s default logger writes the request line including the query
   string; Studio overrides `log_message`. The query builder's values, the
   audit filters and the launch key never reach a log.

## Consequences

**What this buys.** A hostile page in the human's browser can make the browser
send requests to `127.0.0.1:<port>`, and that is the whole of what it can do:
the cookie is `SameSite=Strict` so it is not sent cross-site, `X-Apg-Studio` is
not a simple header so it cannot be set without a preflight, `OPTIONS` is
refused so no preflight succeeds, and `Host` and `Origin` are checked anyway.
PostgREST's CORS behaviour — measured as no header at all — is not in the
security path either way, because the page never holds a token to spend.

**What it costs.** Rig 24b is the second rig of its kind (D1211 stands) and
adds about three minutes to every offline sweep. The launch URL is in the
terminal's scrollback: a hostile *local* process can read it, which is the
residual Jupyter accepts too, bounded by the process lifetime and by the
token's 900 seconds. Studio is single-user by construction — one process, one
token, one cookie; two humans want two processes.

**What it does not decide.** Retention for `agent_audit` (stated, not taken);
the server-side audit filters the stage plan asked for (priced, not built —
the view filters over the page it fetched and says what the page is); the
rotation D860 wants (still recommended, no longer implied to be a
precondition).

## Alternatives considered

**The token in the page, with CORS.** Refused, and it is the alternative the
whole design is against. It makes a third party's default the boundary, puts a
credential where a screenshot can carry it, and leaves no place to enforce a
confirmation the page must not be trusted with (ADR 0140).

**Studio as a container.** Refused. It would publish through Docker's proxy,
require Docker on the human's machine for a page of tables, and make the human's
token cross a container boundary to no benefit. `services/docs` is a container
because it is part of a deployment; Studio is not part of a deployment.

**A bind flag with TLS.** Refused (D1245). There is no certificate a workstation
process could get from the edge, and a flag that binds elsewhere without one
would be a switch that turns the decision off.

**A SQL box with an allowlist.** Refused — an allowlisted SQL box is a SQL box,
and the stage plan's stop condition names it. The query builder sends structure
and the process builds one PostgREST `GET` from the IR's own relations, columns
and the capability schema's operator set (D1210); values are URL-encoded as
values, so `,` `.` `(` `)` reach PostgREST as characters and never as syntax.

**A bundle, a framework, or Scalar's renderer.** Refused (D1249). `services/docs`
vendors 230 MB to ship one 2 MB bundle because a schema *reference* wants a
renderer. Studio's views are tables and forms; a dependency that is not there
needs no audit, no lock and no CVE watch.

**Verifying the JWT in Studio.** Refused (D1246). It would make a fourth
verifier of the key set and buy nothing: the deployment refuses a bad token on
the next request anyway, and Studio would have to hold a JWKS to be wrong about.

**Widening `/admin/audit`'s filters so the viewer can ask the server.**
Refused for this session (D1248), and the reason is not only cost: a server
filter would let a viewer ask for `outcome=served` and never see the refusals,
which is exactly what *no summarisation that hides denials* forbids. The page
is fetched whole, rendered whole, and the header says what the page is.

**Reading the deployed document for diagnosis.** Refused (ADR 0158). It is the
address book. The surface answer comes from the served document, and the
capability inspector says in so many words that it is showing the checkout's
compiled lock and that whether the plane serves it is `apg doctor`'s question.
