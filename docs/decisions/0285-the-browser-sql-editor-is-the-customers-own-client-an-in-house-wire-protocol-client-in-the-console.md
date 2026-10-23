# 0285 — The browser SQL editor is the customer's own client: an in-house wire-protocol client in the console, the password held only in the page

- **Status:** Accepted; decision 4's deployed policy string amended by ADR 0288 (`font-src 'self'`, Session 45)
- **Date:** 2026-10-21
- **Session:** 44, Run 1 (`docs/plans/session-44-implementation-plan.md`,
  D2732, D2734, D2735, D2737, D2738, D2744–D2746, D2754–D2757, D2765–D2768;
  rigs 44a, 44b, 44e)
- **Affects:** `services/console/public/pg.js` (new: the wire client),
  `services/console/public/sql.js` (new: the editor's DOM-free logic),
  `services/console/public/app.js` (the editor view, the Connect page's link),
  `services/console/public/pages.json`, `services/console/serve.py` (the
  policy built from one rendered origin; `env.json` gains `sql_relay`),
  `compose.yaml` (the console's third environment name),
  `docs/product-contract.md` §5 (the sentence, Run 5), `docs/reality-ledger.yaml`
  (`sql_editor`, `console`), the console's guards
  (`tests/contract/test_console_server.py`, `test_console_pages.py`,
  `test_console_scram.py`, `test_console_plane.py`, `test_reality_ledger.py`,
  `test_site.py`). Requirements `SQL-CLIENT-001`, `SQL-PAGE-001`,
  `SQL-LIVE-001`.
- **Amends:** ADR 0246's fourth boundary sentence (decision 3 below; 0246's
  status line names this ADR); ADR 0280's Content-Security-Policy constant
  (decision 4) and its decision 6 (*"No project data view"* — the editor is
  the customer's own client, not a data view the platform serves).
- **Related:** ADR 0195 (three outcomes), ADR 0205 (Studio stays loopback),
  ADR 0246 (the hosted boundary), ADR 0261 (`trial`), ADR 0268 (the public
  Postgres door, its cancel reading `:74`, `:97-100`), ADR 0269 (the customer
  roles and their limits), ADR 0276 (sleep), ADR 0280 (the console), ADR 0281
  (its cookies), ADR 0286 (the relay), D2596 (no third-party script), D2592
  (the editor is Session 44's).

## Context

The stage plan's Session 44 asks for a SQL editor in the console that is the
customer's own client: the customer's database password held only in the page,
PostgreSQL's protocol carried over a WebSocket to a relay that holds nothing.
It asked whether a browser driver could keep PostgreSQL's TLS inside the
WebSocket so that the relay saw only ciphertext. WebCrypto exposes no TLS, so
that needs a JavaScript TLS 1.3 implementation — third-party code in the page
that holds the password (D2596 refuses any third-party file in the console), or
cryptography written here. And the door's TLS is the edge's: it terminates at
Traefik (`runtime_override.py:1069-1070`), so "PostgreSQL's own TLS" was never
end to end. **The operator chose on 2026-10-21 (D2732): a wire-protocol client
written here, and a relay that can read the protocol it carries and records
none of it** (ADR 0286).

ADR 0246's sentence — *"a product surface runs no SQL … A customer's own
client, with the customer's own database credential, may"* — was written before
a customer's own client could live inside a product page. No customer role has
a `statement_timeout` and the customer poolers set no `query_timeout`
(D2735): the brief's premise that one bounds the editor is false.

## Measured

- **Rig 44b** (2026-10-21, `~/s44/rigs/44b.txt`): a prototype of the client run
  **unchanged in Node 22.23.2 (`NODE_RUNTIME_IMAGE`) and in Chromium (the pinned
  Playwright image)** through a prototype relay (SSLRequest, TLS with SNI and
  ALPN `postgresql`, verified) to a Traefik 3.7.10 TCP router with
  `baseline.yaml`'s `postgres` TLS option, PgBouncer 1.24.1 behind it in
  plaintext (the `customer-pool` configuration, transaction and session mode,
  a SCRAM userlist holding the role's verifier) and PostgreSQL 18.4 — the
  door's shape:
  1. SCRAM-SHA-256 through WebCrypto authenticated; **the client's proof and the
     server signature it expected equal Python's `hashlib`/`hmac` computation**
     for the logged exchange, in both runtimes; `current_user` = the role,
     `application_name` = `apg-console-editor`. **The control**, a wrong
     password: **`08P01` *"SASL authentication failed"*** — PgBouncer
     authenticates the client itself, so a wrong password through the door is
     never PostgreSQL's `28P01` (D2765).
  2. A server-final with one character of `v=` changed by the relay rig →
     *"the server's signature did not verify; refused before
     AuthenticationOk"* (the control: untampered, reading 1).
  3. `SELECT 1 AS one; SELECT 1/0` → one result, then `22012`.
  4. `COPY (SELECT 1) TO STDOUT` → `COPY 1`, output dropped with a notice;
     `COPY t FROM STDIN` → answered with `CopyFail` → `57014` *"COPY from stdin
     failed: the SQL editor sends no COPY data"*; neither hangs (0.01 s).
  5. **A CancelRequest sent as its own relay session** stops `SELECT
     pg_sleep(30)` cancelled 1 s in: `57014` 1.05–1.08 s after the statement was
     sent, both pool modes, both runtimes; the cancel session closed `1000`.
     The control, `pg_sleep(3)` uncancelled, completed in 3.01 s.
  6. `SELECT generate_series(1, 200000)` with a 1,000-row cap: **the statement
     finished before the cap's cancel arrived** (200,000 rows, 3.29 MB, in
     0.27 s; rows past the cap read and dropped) and the next statement ran.
     **A statement still producing rows** (`SELECT g, pg_sleep(0.0005) FROM
     generate_series(1, 200000) g`) was ended by the cap's cancel with `57014`
     after ~1,380 rows in 1.8 s, both modes, both runtimes; the next statement
     ran (D2766).
  7. WebCrypto's PBKDF2 (4,096 iterations), HMAC-SHA-256 and SHA-256 for a
     fixed vector are equal in Chromium, Node and Python.
  8. The role's connections during a session, read by the client itself:
     1–2, never above its `CONNECTION LIMIT` 2.
- **Rig 44a** (ADR 0286): Chromium blocks a `new WebSocket` to a host the
  policy does not name — a `securitypolicyviolation` for `connect-src` and an
  `error` event, **no request at the edge** (the access log holds none for that
  host); the console host's `__Host-` cookie is **not** sent to the relay's
  name (the control: a WebSocket to the console's own host carries it); binary
  frames round-trip byte-exact (65,792 bytes).
- **Rig 44e** (`~/s44/rigs/44e.txt`): Node 22 imports a module that imports
  nothing and takes `call` and `connect` as arguments; with a stub for each,
  every state `control_states` defines was walked: `sleeping`, `suspending` and
  `starting` opened no socket; `ready` and `updating` opened one, with the
  door's own `user` and the password reaching only `connect`; a `409
  not_available` from `/connections` → *not offered*. **The control**: a module
  that touches `document` at import fails in Node (`ReferenceError: document is
  not defined`) — so `app.js` cannot be the tested module.

## Decision

1. **`services/console/public/pg.js` is the customer's client, written here.**
   PostgreSQL protocol 3.0 over a binary WebSocket. The StartupMessage carries
   `user`, `database` and `application_name=apg-console-editor`, nothing
   else. **Authentication is SASL SCRAM-SHA-256 and nothing else**: any other
   authentication request is refused. The client-first message is `n,,n=,r=`
   with an 18-byte nonce from `crypto.getRandomValues`; the server-first
   message is refused unless its nonce extends ours **and its iteration count is
   at least 4,096** (D2767: anything between the page and the door that rewrote
   it could otherwise make an offline guess cheaper); the proof is computed with
   WebCrypto's PBKDF2, HMAC and SHA-256, the primitives `scram.js` already uses;
   **the server's signature is verified before `AuthenticationOk` is
   accepted**, and a server that skips it is refused. Then only the **simple
   query protocol**: `RowDescription`, `DataRow` in text format,
   `CommandComplete`, `EmptyQueryResponse`, `ErrorResponse` and
   `NoticeResponse` fields, `ParameterStatus`, `BackendKeyData`,
   `ReadyForQuery`; `CopyInResponse` is answered with `CopyFail`;
   `CopyOutResponse` is read and dropped with a notice; `CopyBothResponse`
   closes the session. **No third-party file enters the console** (D2596
   unchanged).
2. **The password lives in the page for the least time** (D2756). One
   `<input type="password" autocomplete="off">` in a form whose submit is
   intercepted (`form-action 'none'` holds); read once into the connection's
   closure; **the input cleared at once**; the closure drops it on disconnect,
   on leaving the view and on `pagehide`. Never storage, a URL, a fragment, a
   log or a request to `/v1`. SCRAM proves it, so neither the relay nor the
   door receives it. The page never offers to remember it; the Connect page
   links *"Open the SQL editor"*, and its rotation is how a person who lost the
   password gets a new one.
3. **ADR 0246's fourth boundary sentence is amended** (D2734) to: *"no product
   surface runs SQL on the platform's side or holds a credential that opens a
   project's data; the console may host the customer's own client, which
   speaks with the customer's own credential through a relay that holds none
   and records none of what it carries"* — the brief's words plus the clause
   D2732 makes honest. *"An agent never does"* and
   `docs/product-contract.md`'s *"Arbitrary SQL execution by an agent, under
   any authentication"* are unchanged. The product contract takes the same
   words in Run 5. The DX hardening guard (dev, generate and Studio run no SQL)
   is unchanged.
4. **ADR 0280's policy constant becomes one function of one rendered origin**
   (D2744): `serve.policy(relay_origin)` returns ADR 0280's string with
   `connect-src 'self' <relay_origin>`, built once at start from
   `APG_CONSOLE_SQL_RELAY_ORIGIN` (`naming.sql_relay_origin`, passed by compose
   as `${…:?required}`). A value that is not exactly `wss://<host>` — a
   `ws://`, a `*`, a path, a port, empty — **refuses to start**. On the deployed
   host:

   ```
   default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:;
   connect-src 'self' wss://sql.agenticpostgresql.com; font-src 'none';
   base-uri 'none'; form-action 'none'; frame-ancestors 'none'
   ```

   `/console/env.json` gains `"sql_relay"` beside `"api"`, so the page types no
   origin. The site's policy (`connect-src 'none'`) is untouched.
5. **The editor exists where the project has doors** (D2738). It reads `GET
   /v1/projects/{key}/connections`; a `409 not_available` is the Connect page's
   *not available* text and no control renders. The two doors — `host`,
   `port`, `user`, `database` — come only from that answer. The view's Ledger
   rows are `sql_editor`, `pooled_endpoint` and `direct_endpoint`. Branch doors
   are not offered in this session.
6. **Only the control API can say *asleep*** (D2737, D2768). Before every
   connect the page reads `GET /v1/projects/{key}`: `sleeping`, `suspending`
   or `starting` → *"This project is asleep. Wake it from Settings, then
   connect."*, and no socket opens; `ready` or `updating` → connect;
   `creating`, `deleting` or `deleted` → *"The project is <state>; nothing was
   opened."* (the state was read, so it is named); `unknown`, any other value or
   a failed read → *"The project's state could not be read; nothing was
   opened."* A relay close `4502` is *"The database could not be reached."* —
   never *asleep*: a sleeping door and a wrong name fail identically in the
   handshake (ADR 0268 `:68,73`).
7. **The editor bounds its own statements** (D2735, D2754, D2766). A Cancel
   control, and an automatic cancel **60 s** after a statement is sent
   (`STATEMENT_DEADLINE_SECONDS`), each a CancelRequest (code 80877102, the pid
   and key from `BackendKeyData`) sent as the first message of **its own relay
   session** to the same door, so it arrives encrypted — the only cancel the
   door is known to pass. **The next statement is sent only after a cancel's
   session has closed**, so a cancel that lands late cannot reach it. The page
   says beside the editor *"A statement still running after 60 seconds is
   cancelled."* PostgreSQL and PgBouncer decide everything else: the role's
   grants, row-level security, its `CONNECTION LIMIT`. Nothing about a role
   changes for the editor.
8. **Results are bounded by the page** (D2755, D2766): at most 1,000 rows and
   2 MiB of row text per statement; past either, rows stop being kept, a cancel
   is sent, and the page says *"Showing the first 1,000 rows; the rest were not
   read."* — **its own cap's `57014` is shown as that sentence, never as an
   error**. Multi-statement input shows every result in order; the first error
   ends the batch as PostgreSQL does. Cells are text nodes only. No export, no
   download, no history.
9. **The logic is a DOM-free module** (rig 44e): `services/console/public/sql.js`
   imports nothing and takes `call` (from `api.js`) and `connect` (from
   `pg.js`) as arguments; `app.js` only renders and wires. Its tests run it in
   the pinned Node image with stubs (`test_console_sql.py`); `pg.js` is tested
   in Node against PostgreSQL through PgBouncer and the relay
   (`test_console_pg.py`).
10. **Every console guard is kept and extended, never loosened** (D2745):
    `test_no_script_holds_sql` and `test_no_script_writes_storage` unchanged
    (they now cover `pg.js` and `sql.js`); a new `test_only_pg_js_opens_a_websocket`
    beside `test_only_api_js_calls_fetch`; the scripts' name list gains `pg`
    and `sql`; the routes gain `/console/pg.js` and `/console/sql.js`; the
    console's environment is exactly three names; the policy test asserts the
    exact string for a fixture origin, a second asserts every other directive
    byte-equal to ADR 0280's, a third refuses each bad origin.
11. **The Ledger moves with the evidence** (D2746, ADR 0261): the editor view
    lands behind a named exception for `sql_editor` in the page guard (Run 5),
    removed at the bump, where the row moves `planned` → `trial`; it moves to
    `beta` at the close only if its claims passed.

## Alternatives

- **A vendored TLS-in-WebSocket implementation**, so the relay carried only
  ciphertext. Rejected by the operator (D2732): it puts code nobody here
  reviewed into the one page that holds the password. What it would have
  bought — a relay blind to the protocol — is recorded as what this design
  gives up (ADR 0286, threat item 25).
- **A third-party PostgreSQL driver for the browser.** The same objection
  (D2596), and none speaks to a raw WebSocket without a server of its own.
- **A server-side SQL endpoint** (the platform runs the statement). Never: it
  is exactly what ADR 0246 forbids, and it would hold a credential.
- **A hosted Studio.** ADR 0205: a second server holding a member's token.
- **The extended query protocol.** More surface (parse, bind, describe,
  portals) for nothing a person typing statements needs.
- **A `statement_timeout` on the customer roles.** It would change what every
  client gets, `psql` included — a product decision this session does not
  take (threat item 26).

## Consequences

- The console holds a database password for the length of an editor session.
  Its policy, its first-party-only rule and the closure are what keep it there.
- A wrong password through the door reads `08P01`, not `28P01`: every proof and
  every sentence the page shows reads PgBouncer's answer (D2765).
- A customer's `psql` still has no deadline; the editor's 60 s is the editor's.
- The editor is offered on slots only, and on their main doors only.
