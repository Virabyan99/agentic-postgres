# Session 24 — Studio, and the trip two sessions owe

**Status:** **PLANNED 2026-09-12** at `035192d`, Session 23's close, on
`main`. **Runs 1, 2 and 3 are Done** (2026-09-12, on branch `session-24`);
Runs 4–7 are ahead. §1 was D1243–D1258 at planning (each read from the tree at `035192d`),
and Run 1 added **D1259–D1262** and rewrote four with their numbers; the
runs add theirs below, so **next free is D1282**.
ADR **0205** is this session's (written in Run 1); next free after it 0206.
**Brief:** `docs/plans/stage-3-plan.md` §5 *Session 24 — Studio* whole (Builds
/ Already true / Must not / Measures / Closes), its rows D1069 (one Studio, a
loopback client, the query runner is REST and never SQL), D1074 (each building
session ships its own negative tests), D1079 (first paint in the envelope);
§8's five rows that name this session (*PostgreSQL is the final authorization
authority*, *a human cannot run SQL through a product surface*, *the DX layer
holds nothing the human does not hold*, *a revoked token stops on its next
request*, *a report may not substitute an answer*); §9's stop condition (*a
Studio feature needs SQL, a non-loopback bind, or a credential beyond the
human's*); §10's two items 24 must STATE (the rotation performed, D860; the
audit table's retention). Plus everything Sessions 22 and 23 left to *the next
trip* — `docs/plans/session-22-implementation-plan.md` §10,
`docs/plans/session-23-implementation-plan.md` §10, `docs/scope-closure.md`
§11–§12, and `CLAUDE.md` §2's two *WHAT SESSION 24'S TRIP OWES* lists.
**Shape:** seven runs on a `session-24` branch, CI green on every commit that
changes code; Runs 1–6 offline; **Run 7 is a host trip**, the first since
Session 21, and it is ONE trip that pays three sessions' evidence (D1244).
**Product version at close:** `CURRENT_SESSION` 24; `template_version`
proposed **`1.5.0`** — a new operator command (`apg studio`), ONE released
migration (`0032`, the audit reader returns the boundary that refused), one
additive field on one administrative endpoint's response; no manifest,
outputs, capability, lock or secret schema moves (ADR 0162: `migration_added`
is minor; confirmed by Run 7's `upgrade plan`, and a `major` there is §9's
stop).
**Written for whoever picks this up cold, and it will be a different model
than the one that planned it.** Every path is exact. Every third-party claim
below is either measured in a rig in Run 1 with a control, or marked as the
measurement Run 1 owes — never assumed. Read `CLAUDE.md` §1 in the launch
folder before the first command, then this plan's §1, then the appendix. If a
step here and the tree disagree, **the tree wins and the disagreement is a
divergence row**, never a silent reconciliation.

---

## 0. Where the session starts

Session 23 shipped `apg generate` (ADR 0204) and closed on an offline half;
Session 22 shipped `apg dev` (ADR 0202, 0203) and did the same. **The host has
not been touched since Session 21**: checkout `f61f716`, deployed release
`f61f716` on both projects, `deployed_through_session` 21, alpha 6 tools /
beta 7, 31 migrations applied on alpha and 32 on beta. Four host claims are
`not_run` by construction — `plane_confirmed_count`, `agent_tenant_read`
(22's), `generated_client_hash`, `agent_lock_reported` (23's) — and two
three-half merges are owed. This session's trip pays them (§5 Run 7, §7).

**What a human's view of a deployment is today, measured at `035192d`.**
There is no Studio (`git grep -in studio` finds `bin/connect.sh` refusing
`prisma-studio` and nothing else). A human who wants to see their rows types
`bin/api.sh` operations under `dev-token.sh` (root's), or reads the Scalar
page at the docs route behind a Basic password materialised for Traefik and
handed to nobody (`bin/docs.sh` header). A human who wants to see what an
agent did calls `GET /admin/audit` with a token carrying `admin_audit:read` and
reads JSON. **What that endpoint returns does not include the boundary that
refused** (D1247): migration 0027 added `denial_reason` to the table and never
widened the 0020 reader, and `routes.py` serialises no such key. A human who
wants to revoke an agent sends `PATCH /admin/agents/{id}` with
`{"status": "revoked"}` — one request, no confirmation shape, and nothing in
`bin/` wraps it.

**What exists and is not rebuilt** (every surface Studio clients — stage plan
*Already true*): the REST route as the human's token (RLS applies; `GET /`
with `Accept: application/openapi+json` serves the surface to the
`authenticated` role at fingerprint `808ac715…` on the example project — rig
23a); `POST /auth/login` → `{access_token, expires_at, token_use,
refresh_token}` with `Cache-Control: no-store`; `POST /auth/refresh`; `GET
/auth/me`; `GET /auth/sessions` → `[{session_id, created_at, last_used_at,
revoked_at, revoked_reason}]` and `DELETE /auth/sessions/{id}` → 204 either
way; `GET /admin/agents` (`admin_agents:read`), `PATCH /admin/agents/{id}`
`{status: active|revoked}` (`admin_agents:write`), `GET /admin/audit?agent_id
&owner_id&limit` (1–500, default 100, `admin_audit:read` — in the
administrator's ceiling and no other); the human token's lifetime
`claims.MAX_TTL_SECONDS` (900 s, `service.py:36`); the scope ceilings
(`scopes.py:60-128`); the compiled lock and the IR that carries it
(`client_ir.build`, GEN-IR-001: relations with columns and types, RPCs,
tools with arguments and scopes, `filter_operators()` from the capability
schema, four digests); `openapi_normalize.normalize/fingerprint` (the
capture's own, D1207); the docs service's CSP and its fixed-table server
(`services/docs/serve.py:98-124`, ADR 0069 — the shape Studio's server
copies); `apg dev` and the Session 23 runtime rig (`tests/contract/
test_generated_client_runtime.py:217-410`: a dev cluster, PostgREST from
`compose.yaml`'s own block, Traefik stripping the prefix); the auth
application driven in-process against a dev cluster
(`tests/contract/test_auth_endpoints.py:116-410`: `cluster`, `signing_key`,
`administrator`, `environment`, `create_app("auth")`); `--confirm KEY`
(`bin/edge.sh`, `bin/bootstrap-providers.sh`: the value must equal the
identity of the thing acted on); the `--admin-password-file` shape and the
deployment suite's `admin_session` / `audit_admin` / `create_reader` /
`mcp_rpc` fixtures; `dev-token.sh`'s rule that a credential reaches a process
through its environment or a 0600 file and never an argument (D105).

**What this session builds, in one paragraph.** `apg studio --project FILE
--outputs FILE [--username NAME] [--password-file FILE]`: a **single Python
standard-library process** (`bin/studio.py`, pure logic in
`src/agentic_postgres/studio.py`) that (1) builds the project's IR from the
same four committed inputs `generate` reads, (2) logs the human in through
`POST /auth/login` on the deployment named by the deployed document
(password from a TTY prompt or a 0600 file, never an argument, never the
environment), (3) fetches the served REST document AS THAT HUMAN and answers
one of four ways exactly as a generated client's `init()` does — `ok`,
`stale_contract` naming both digests, `unreachable`, `unreadable` — refusing
the REST half of the UI on anything but `ok`, (4) binds
`ThreadingHTTPServer` to `127.0.0.1:0` (no other address exists in the code;
there is no flag), prints ONE URL carrying a per-launch key, and serves three
first-party files (`services/studio/index.html`, `studio.js`, `studio.css`)
under the docs service's CSP, plus a **same-origin forwarder** under
`/__apg/` — an enumerated table of operations (the `bin/api.py` shape) each
mapped to exactly one upstream request built by the process from validated
parts, sent with the bearer the process holds in memory. **The browser never
holds the token**: it holds a launch cookie (`HttpOnly`, `SameSite=Strict`),
and every forwarded request must carry that cookie, a `Host` equal to the
bound address, an `Origin` (when present) equal to the page's own, and the
header `X-Apg-Studio: 1`; `OPTIONS` is refused, so no cross-origin preflight
ever succeeds. The UI: a schema browser rendered from the IR (which `ok`
proved equal to the served document); a **query builder** over the reviewed
relations — columns from the IR, operators from the capability schema, values
sent as values — that the forwarder turns into one PostgREST `GET`; an
**audit viewer** over `GET /admin/audit` that renders EVERY row of the page it
fetched, shows the boundary that refused (migration 0032), filters
client-side and says *n of m shown* rather than hiding a denial; a
**capability inspector** from the compiled lock in the IR, which says it is
the checkout's lock and names the command that asks the plane; an **agent
list** with **revocation** as the existing `PATCH`, behind a typed
confirmation the forwarder checks server-side against the path's agent id.
On exit Studio ends the session it began (`DELETE /auth/sessions/{id}`) or
prints that it could not determine which (ADR 0195). First paint in the
envelope. One released migration. A `STU-*` family, three claims, one trip.

**What it does not build, by decision** (§1): a SQL box of any kind
(D1069, product-contract §5 — refused, not deferred); a non-loopback bind
under any flag (D1245); a bundle, a framework, an npm lock, or any line of
third-party JavaScript (D1249); a verifier of the JWT (Studio sends the
token; it never validates it — D1246); a reader of the deployed document for
diagnosis (ADR 0158: it is the address book and nothing else); a second
canonical form (Studio fingerprints with `openapi_normalize`, Python's own);
a widening of `/admin/audit`'s filters (D1248: the page is fetched whole and
filtered in view, with the page's boundary shown); a data write of any kind
through the query builder; an agent-token path (Studio never calls the MCP
route — a human's token is not an agent's, and the plane's answer is `apg
doctor`'s and the generated client's question); PostgREST as an `apg dev`
verb (D1211 stands; Studio targets a deployment, and the offline rig is a
rig); retention for the audit table (stated in §10, not taken).

**Read before touching anything:** ADR 0002 (derive an identity once), 0050,
0065/0066 (a rig is a second configuration and must be tied to the product's),
0069 (the docs page's CSP is ours — the shape Studio copies), 0087, 0093
(an operator command imports only what the host has), 0095/D298 (a token the
suite signed proves the suite can sign), 0097 (what a refusal may say), 0117
(`token_use` is the discriminator), 0135 (audit written as the caller), 0140
(hiding a control is not a boundary — the reason Studio's forwarder validates
server-side and never trusts the page), 0141 (a denial is audited), 0142
(`admin_audit:read`), 0155 (a deploy recreates a container whose mount
moved), 0158, 0162 (what a bump permits), 0171 (the session plane), 0175
(every call to a released function is checked against its arity — 0032 keeps
the arity), 0178 (a denial names its boundary — the column 0032 exposes),
0195, 0198/0200/0201, 0202/0203/0204; D105 (nothing prints a token), D433
(never relay an upstream status), D486 (a second copy is a compared pair),
D600 (a null that looks measured), D941 (read the ledger, never the
migrator's line), D972 (never redirect a sudo deploy), D1114/D1117 (a proof
calls the product's own command), D1152/D1153 (read the container, never the
file), D1172 (Docker's loopback publication, measured), D1184 (`document`
means the deployed document in a `bin/` command), D1187 (a move greps the
moved text), D1199 (a gate's last lines are the least executed), D1210 (the
operator set is the capability schema's, for humans too), D1238 (a release
bump owes a client regeneration in the same commit), D1240/D1242 (collected,
and by which sweep).

---

## 1. The divergence table

Six columns, next free number after this table **D1282** (Run 1 added D1259–D1263; Run 2 D1264–D1267; Run 3 D1268–D1273; Run 4 D1274–D1275; Run 5 D1276–D1277; Run 6 D1278–D1281). Rows D1243–D1258
were read from the tree on 2026-09-12 at `035192d`; where a row's *Repository
does* column says *measure*, Run 1 owns the measurement and the row is
rewritten with the numbers.

| # | Said | Repository does | This session | Why | ADR |
|---|---|---|---|---|---|
| **D1243** | Stage plan §5 Session 24: *"a local web UI bound to `127.0.0.1` only … holding nothing but the human's short-lived token"*; the token is *"from `/auth/login`, never minted by `dev-token.sh`"*. Session 22's D1172 measured Docker publishing `-p 127.0.0.1:0:5432` as `LISTEN 127.0.0.1:32768` against `*:32769` for the control. | **Nothing in the tree serves a page to a human on a workstation.** `services/docs/serve.py` is the one first-party HTTP server: `http.server` + `socketserver`, a fixed path table, our own CSP — and it runs in a container on the edge network. Studio is not a container: a container needs Docker and publishes through Docker's proxy (D1172's WSL2 caveat), and the human's token would cross a container boundary for nothing. **Where the token lives is the design.** A page that held the bearer (in JS memory, `localStorage`, a query string) is one XSS or one shared screenshot from a credential leak, and every request it made would be cross-origin to the deployment (a page on `127.0.0.1` calling `https://beta-db…`), which puts CORS — a third party's default — in the security path. | **Studio is one stdlib process bound to `127.0.0.1:0`, and it is a same-origin forwarder.** The browser holds a per-launch cookie and never the token; the process holds the token in memory and makes every upstream request itself from an enumerated table; `Host`, `Origin`, the cookie and one custom header are checked on every forwarded call; `OPTIONS` is refused. **Measured, rig 24a, 2026-09-12.** `ss -ltn` shows the loopback server at `127.0.0.1:34273` and the CONTROL — the same class bound to `("0.0.0.0", 0)` — at `0.0.0.0:39573`; read a second way because a test may not have `ss`, a `socket.connect` from this host's own interface address is refused by the loopback server (`ConnectionRefusedError`) and **connected** by the control, while `127.0.0.1` reaches it. (`socket.gethostbyname_ex(gethostname())` offers only `127.0.1.1` here, so the interface address is read from the interface — the fallback path's own finding.) `http.server` exposes `Host`, `Origin` and `Cookie` as sent, and all nine arms answered as designed, each with its passing control in the same invocation: no cookie → **401**, `/open/<key>` → **303** with `Set-Cookie: apg_studio=…; HttpOnly; SameSite=Strict; Path=/`, with the cookie → **200**, foreign `Host` → **421**, foreign `Origin` → **403**, own `Origin` → **200**, `OPTIONS` → **405**, `POST /__apg/` without `X-Apg-Studio` → **403**, with it → **200**. Every refusal was sent with `self.rfile` untouched: a refused `POST` announcing `Content-Length: 1000000` with one byte sent is answered 403 with `Connection: close` and does not hang the client. | The stage plan's *must not* list is a list of things a client does not have; the cheapest way to be sure the page cannot leak a token is for the page never to have one. ADR 0140: hiding a control is not a boundary — so the checks are in the process, never in the page. | 0069, 0140, **0205** |
| **D1244** | `CLAUDE.md` §2: *"PRICE THE TRIP FIRST … 24 owes TWO separate three-half merges (22's and 23's) BEFORE any Studio work"*. Stage plan §5: Session 24 *"ends on a host for the one proof that matters"*. Read together: two trips. | **Two trips cost two sudo sheets and two 15-minute sweeps**, and the operator has said one sweep per trip is what a trip may cost (memory: *host-trip-shape*). The evidence writer takes `--junit` repeatably (`write-session-evidence.py:411`, `action="append"`) and `--session N` separately, and `claims_through_session(N)` is cumulative — so ONE host sweep by the newest gate produces a JUnit that answers 22's, 23's and 24's host claims, and the writer run three times over it writes three host halves. `upgrade plan` reads only (`bin/upgrade.sh` header) and takes any `--candidate`, so 1.3.0 and 1.4.0 can each be PRICED from a rendered candidate without being deployed. | **One trip, Run 7, paying three sessions.** The deploy is `--through-session 24` (which is ≥22 and ≥23: applies the example set's second migration on beta, `0032` on both, and recreates auth/mcp — everything the two lists ask for). One cumulative host sweep, one external run; the writer invoked for 22, 23 and 24 over the same halves; three merged documents; three upgrade plans from three candidates (`8823877e`, `2121c029`, this session's bump) against the installed 1.2.0. The cost named: a claim of 22's measured against release 1.5.0 rather than 1.3.0 — which is what would happen anyway, since no trip can deploy a release that is not the checkout's head, and ADR 0202's writer prints the difference rather than hiding it. | The handoff's *BEFORE* was about attribution, not about count: a 22 claim failing on a 1.5.0 deployment must be read, not folded. One sweep with the reading owed is cheaper than two sweeps, and the reading is owed either way. | 0202, D1163 |
| **D1245** | Stage plan *Must not*: *"Bind a non-loopback interface without an explicit flag, and even then never without TLS it did not get from the edge."* | **There is no TLS Studio could get from the edge**: the edge terminates for the deployment's domain, and a workstation process is not behind it. A flag that binds elsewhere would need its own certificate, its own CSP origin, and a threat model for a token-holding process on a LAN — none of which this session builds. | **No flag. `127.0.0.1` is a constant** (`studio.BIND_ADDRESS`), and the test asserts the listener by `ss -ltn`/`socket` rather than by reading the constant. A person who wants Studio on another interface edits the source, which is the boundary this project uses for every other refusal it does not want to make configurable (`dev-token.sh`: *"adding one would be a change to the security posture"*). | A refusal with a switch is a decision deferred to whoever finds the switch (D694). | **0205** |
| **D1246** | Stage plan §10: *"Studio makes a FOURTH verifier of the key set"*, and D860's rotation is *"recommended before Session 24 adds a fourth verifier"*. The same plan's *Must not*: *"Become a verifier of the JWT in its own right — it sends the token, it does not validate it."* | The two sentences contradict each other and the second is the design. A verifier reads the JWKS and checks a signature; Studio does neither — it forwards `Authorization: Bearer` and reads status codes. **Studio is a HOLDER, not a verifier**: the verifier count stays four (PostgREST, auth, storage, the plane; ADR 0170). What a rotation must recreate is unchanged by this session. | The rotation performed (D860) stays **recommended and is not a precondition** of this session; §10 states it as the standing item it is. Studio's proof that it verifies nothing: `test_studio_holds_no_key_and_verifies_nothing` — the module imports no `jwt`, `jwks`, `cryptography`, and a token the deployment refuses is forwarded and refused upstream (401 relayed as `refused`, D433's rule: a classification, never the body). | A premise wrong in the reassuring direction survives longest (D930); this one was wrong in the alarming direction and would have cost a rotation sequence nobody planned. | 0170 |
| **D1247** | Stage plan §5: the audit viewer shows *"every denial and failure"*, *"filterable by agent, capability, outcome, boundary and time"*, *"no summarization that hides denials"*. ADR 0178: a denial names its boundary, in `agent_audit.denial_reason` (migration 0027). | **`GET /admin/audit` does not return the boundary.** `auth_list_agent_audit` (0020, `RETURNS TABLE` at lines 88–100) predates 0027 and was never widened; `git grep -n denial_reason services/auth-api` finds nothing; `routes.py:1010-1046` serialises `id source agent_id owner_id tool request_id parameters outcome row_count elapsed_ms started_at completed_at limit`. So the one read path to the record (ADR 0142) shows a refusal WITHOUT which boundary refused — a viewer built on it would show every denial and hide the one thing ADR 0178 exists to record. | **Migration `0032-agent-audit-reader-boundary.sql`** (Run 2): `DROP FUNCTION app_private.auth_list_agent_audit(uuid, uuid, integer)` and re-`CREATE` it with `denial_reason app_private.agent_denial_reason` appended to the `RETURNS TABLE`, same three arguments (ADR 0175's arity guard is untouched), `REVOKE … FROM PUBLIC` and `GRANT EXECUTE … TO {{auth_service}}` re-issued (a `DROP` drops its grants — 0020 lines 131–154 say why the grant is there). `routes.py` serialises `denial_reason` (null on every non-refusal, by 0027's CHECK). `app-contract.sh --update`, the client regenerated (D1238), `migrate.sh freeze-lock`. A NEW requirement, **`AGT-AUDIT-002`**: *the audit read returns the boundary that refused, exactly on refused rows*, proved offline against a cluster and live on alpha after a real refusal. **Measured, rig 24c, 2026-09-12**, on a cluster with all 33 migrations applied: the reader returns twelve columns and no `denial_reason` (`pronargs` 3), and asking the function for the column errors `column "denial_reason" does not exist` — D1247 confirmed rather than assumed. `CREATE OR REPLACE` with the widened `RETURNS TABLE` is refused by PostgreSQL 18.4: **`cannot change return type of existing function`**, so DROP + CREATE it is (the plan's sentence stands; §9's alternative did not arise). The grant really does go with the DROP: between the CREATE and the re-issued GRANT the auth service is answered `permission denied for function auth_list_agent_audit`, and after it reads both rows — the `refused` row carrying `scope_not_held` (0027's first enum member) and the `served` row `NULL`. `pronargs` 3 before and 3 after. | A record that names the boundary and a reader that drops it is D816/D929 at the endpoint: a declared field with no reader. This is the kind of defect a viewer finds because a viewer is the first reader that shows the whole row to a person. | 0142, 0175, 0178 |
| **D1248** | Stage plan: filterable by *"agent, capability, outcome, boundary and time"*. | The endpoint's query is `agent_id`, `owner_id`, `limit` (1–500) — `routes.py:311-321`, `strict_query`. No outcome, no boundary, no time window, no cursor. Widening it is a second migration (the reader takes three arguments and the arity guard reads every call site), a query-parameter contract change, and a page-through design nobody has priced. | **Server-side filters stay what they are; Studio filters IN VIEW over the page it fetched, with `limit=500`, and the viewer's header always reads `showing n of m rows on this page; the page is the newest 500` — every row of the page is in the DOM, filters hide nothing from the page's count.** The measurement the stage plan asks for is kept exactly: the page's row count equals `SELECT count(*) FROM (SELECT 1 FROM app_private.agent_audit ORDER BY started_at DESC LIMIT 500) s` as root over the socket (offline: over the rig's cluster). The widening is §10's, priced. | *No summarisation that hides denials* is satisfied by rendering the page whole and saying what the page is; it is NOT satisfied by a server filter that would let a viewer ask for "outcome=served" and never see the refusals. The client-side filter is a display choice with the total beside it. | 0195 |
| **D1249** | Stage plan §1.4.7 (via D1074): *"SBOM and dependency supply-chain audit"* for Studio; *Already true*: *"the CSP discipline of `services/docs`"*. | `services/docs` vendors a 230 MB Scalar install to ship one 2 MB bundle, under a lock with integrity hashes, because a schema *reference* wants Scalar's renderer. Studio's views are tables and forms. | **Studio ships zero third-party code**: three hand-written files, no `package.json`, no `node_modules`, no build step, no CDN, no font; CSP `default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'` (stricter than the docs page's — no `'unsafe-inline'`, because nothing here writes styles at runtime). `test_studio_assets_carry_no_third_party_code`: no `://` outside comments in the three files, no `<script src` to anything but `studio.js`, no `package*.json` under `services/studio/`. **The SBOM is the Python standard library and three files.** | A dependency that is not there needs no audit, no lock and no CVE watch. The generated client took the same decision for its runtime (no dependencies) and it held. | 0069 |
| **D1250** | Stage plan: the query runner is *"a PostgREST query builder — filters, ordering, limits over the reviewed views — as the human's token."* | `client_ir.IR` already carries every reviewed relation with its columns and types, the enum vocabulary and `filter_operators` (the capability schema's closed set, `evaluation_harness.filter_operators`); `test_a_filter_value_is_a_value_and_never_query_syntax` (Session 23) is the shape of the value rule. Nothing in the tree turns a structured query into a PostgREST URL in Python — the generated client does it in TypeScript. | **The browser sends structure, the process builds the URL.** `studio.rest_query(ir, relation, select, filters, order, limit) -> str` is pure and refuses: a relation the IR does not name, a column not in that relation, an operator not in the set, `limit` outside 1..`STUDIO_MAX_ROWS` (a named constant, 1000, because a human's page is not an agent's budget), a value containing anything it would URL-encode unencoded. Every value is `urllib.parse.quote`d as a VALUE (`col=eq.<value>`), so `,` `.` `(` `)` in a value reach PostgREST as characters and never as syntax; the proof sends `a,b)or(1=1` as a value and gets zero rows, with the control that the same string as a stored value is found by `eq`. The operator set is the capability schema's for humans too (D1210 restated). | A URL the page composed would be trusted input; a URL the process composed from validated parts is a query the reviewed surface permits. Reads only: there is no `POST`/`PATCH`/`DELETE` to the REST route in the table at all. | 0127, D1210 |
| **D1251** | Stage plan: *"Revocation as the existing admin endpoint, one click, with the same confirmation shape `--confirm KEY` gives a shell."* | `PATCH /admin/agents/{agent_id}` with `{"status": "revoked"}` under `admin_agents:write`; `--confirm` in the tree means *the value must equal the identity of the thing acted on* (`edge.sh:300-302`, `bootstrap-providers.sh:211-213`), and a mismatch says what was expected and that nothing changed. `agent_claims_are_current` (0018) returns NULL for a revoked agent, so the NEXT request stops (SEC-REV-001's two offline proofs). | **The forwarder's `revoke_agent` operation takes `{agent_id, confirm}` and refuses `confirm != agent_id` with 422 and the message the shell gives** (`--confirm said X but this agent is Y. Nothing was changed.`) BEFORE any upstream request; the page asks the human to type the id. The live proof (Run 6's module, Run 7's sweep): an agent created on alpha (`create_reader`'s shape), `list_resources` → served, revoke THROUGH STUDIO'S FORWARDER (an HTTP request to the loopback server with the launch cookie — the product's own path, D1114), the agent's next `list_resources` → refused, `POST /auth/agent-token` with its secret → 401, and the refusal's audit row VISIBLE in the viewer with its boundary. | A one-click revocation with no confirmation is the shape D694 refuses; a confirmation the page checks and the process does not is ADR 0140's hidden control. | 0140, 0171 |
| **D1252** | Stage plan: Studio *"launched with the human's own short-lived token"*; the session plane (ADR 0171) lists and ends sessions. | `POST /auth/login` returns no session id; `GET /auth/sessions` rows carry `session_id, created_at, last_used_at, revoked_at, revoked_reason`; the access token lives `MAX_TTL_SECONDS` = 900 s and the refresh token rotates a family. Studio open for an hour must refresh; Studio closed must not leave a live family behind. | **Studio refreshes** through `/auth/refresh` when fewer than 120 s remain (the constant `STUDIO_REFRESH_BEFORE_SECONDS`), and **ends the session it began at exit**: immediately after login it lists sessions and takes the live row with the newest `created_at`; if two rows share that instant it records `session_id = None` and at exit prints *"Studio could not determine which session was its own and ended none; `GET /auth/sessions` lists them"* — ADR 0195, the third answer reported. **Measured, rig 24b, 2026-09-12**: one login → exactly **one** row, live, with keys `session_id, created_at, last_used_at, revoked_at, revoked_reason`. `created_at` has **microsecond** resolution — three logins inside 0.68 s produced three distinct values, so the tie branch is unreachable in practice and is proved as a unit, not in the rig. A proof for each of the three paths (determined and ended; refresh performed; undetermined and reported). | A session a tool opened and could not close is a credential with nobody's name on it; a tool that guessed which to close might close the wrong one. | 0171, 0195 |
| **D1253** | Stage plan: *"the schema browser reuses the served OpenAPI (the docs route already renders it; Studio reuses the documents, not the bundle)"*. ADR 0204: a client is a claim about the surface it was generated from, checked at `init()` against the SERVED document as the caller. | The docs route serves the FILE the deploy mounted, behind Basic auth a human cannot hold (rig 23a). The served REST document to the `authenticated` role IS the committed snapshot's fingerprint, and the IR is built from that snapshot. | **Studio does what `init()` does, in Python**: at launch, `GET <rest>/` with the human's bearer and `Accept: application/openapi+json`; `openapi_normalize.normalize` + `fingerprint`; compared to `ir.digests.rest_openapi_sha256`. `ok` → the schema browser and query builder are served from the IR (proved equal); `stale_contract` → the REST half of the UI is refused, both digests shown and `bin/apg.sh generate --project <path>` / the capture named; `unreachable` and `unreadable` are two different answers with the reason. The audit, agent and session views (the application surface) stay available in every state: they are release operations, not project ones. No second serializer (D1203 stands: the fingerprint is Python's own function, the one the capture uses). | The IR is a checkout's belief; the served document is the deployment's. Studio may render the belief only after the deployment has confirmed it, which is the sentence ADR 0204 wrote for clients and applies to a UI unchanged. | 0158, 0204 |
| **D1254** | `apg dev` is *"the database"* and nothing more (ADR 0203, D1157); PostgREST beside it is a rig (D1211). Studio needs a deployment: a REST route AND an application route. | On a workstation there is no deployment to point Studio at except a real one (op-owned deployed-document copies exist: `alpha-outputs.json`, `beta-outputs.json` in the checkout root, gitignored). `bin/api.py:80-90` refuses a `routes.rest.url` that is not `https`. The Session 23 rig publishes nothing on the host: its containers talk on a Docker network and the client runs INSIDE it. | **Studio reads the deployed document as its address book and requires `https` — with one rule, written down: a route whose host is `127.0.0.1` or `localhost` may be `http`, because loopback never leaves the machine (the same reason Studio itself is plain HTTP on loopback).** An `http` URL to any other host is refused with exit 5. **Rig 24b, built and measured 2026-09-12.** It publishes the Session 23 rig's edge on `127.0.0.1:0` (D1172's form; `docker port` read `127.0.0.1:32923`) and adds the real auth application on a loopback port — `uvicorn.Server.run` in a thread, the bound port read from `server.servers[0].sockets[0].getsockname()`, **which exists at the pinned uvicorn 0.50.2** — its published JWKS handed to PostgREST as `PGRST_JWT_SECRET=@/etc/postgrest/jwks.json` (the `@file` form; schema cache loaded in 1.8 s, CONTROL: the HS-secret form `served` uses loads too, so both work at the pinned image), then writes a `document_kind: deployed` document naming both loopback URLs. Timings: `apg dev up` 16.4 s, the auth app ready 0.4 s, PostgREST 1.8 s, the whole rig to its last reading 35.9 s. **The rig's one non-obvious value is D1261's**: the proxy URI must name the loopback host with the `https` scheme. Studio's offline proofs run against THAT document — the product's own command against a rig tied to the product's configuration (ADR 0065/0066). | A flag that names URLs is a second address book; a loopback exception is one sentence with a measured reason. The rig is a rig (D1211 stands), and its cost is stated in Run 1's Done paragraph. | 0065, 0066, 0158, 0203 |
| **D1255** | `CLAUDE.md` §2 and stage plan §10: the audit and idempotency tables *"grow without bound"*; §10 says Session 24 *"must STATE"* the retention decision *"even if it does not take it"*. | `app_private.agent_audit` is append-only to every request role (0019's comment); nothing prunes it or `agent_idempotency`; `GET /admin/audit` reads the newest `limit` rows. On alpha, live, the count is whatever eleven sessions of probes left — unknown until Run 7 reads it. | **Stated, not taken** (§10): retention is an operator decision about a compliance record, and a pruning migration is a released migration with a policy in it. Run 7 records `SELECT count(*)` on both projects as the number the decision starts from. Studio's viewer shows the newest 500 and says so (D1248), so the table's size changes nothing the viewer claims. | A decision taken in a UI session about how long an audit record lives would be the wrong session and the wrong reason. | — |
| **D1256** | Stage plan *Must not*: *"Log a URL, an object key, a token or a caller value (the canary applies)."* | `mcp_telemetry.py` carries the canary's list and the redaction contract; `services/docs/serve.py` logs the request line by `http.server`'s default (`log_message`), which includes the PATH WITH ITS QUERY STRING. | **Studio's server overrides `log_message` to print `METHOD PATH-WITHOUT-QUERY STATUS` and nothing else**, on stderr; the query builder's values, the audit filters and the launch key (a path segment, once) are never written. `test_nothing_studio_prints_is_a_token_a_key_or_a_value`: the whole stderr of a run scanned for the token, the launch key, every filter value sent and the password. | A caller value in a log is the defect Session 7's canary was written for; the default logger would have put one there on the first request. | 0166 |
| **D1257** | The trip (Run 7) also owes: the two `test_honest_readers` proofs AS ROOT (D1165; `sudo -u` re-entry never executed), D1164's owner/mtime confirmation on `.generated/alpha-dev`, the DR kit re-export, `list_resources` on beta reporting the lock, the example client run in the toolchain image on the host. Session 23's §10 lists them; Session 22's §10 lists its own. | Each is a line in one of the two plans' §10, and none is in any gate's arguments — they are readings. | **All of them are in Run 7's sheet, numbered, with the reading each produces named** — none is left to "everything Session 22 owed". | The last three trips each paid for something a previous plan left as a pointer (D977). | — |
| **D1258** | Stage plan: *"First paint against the fixture project in the envelope."* `docs/capacity-envelope.md` has MACHINE rows for `apg generate` (0.28–0.33 s) and the typecheck (1.12–1.61 s). | *First paint* in a browser is not measurable from this workstation (no browser in WSL; the Windows browser is not the product). What IS measurable, with the product's own command: the time from `apg studio` start to the URL printed (IR built, login, surface verified), and the server's time to answer `GET /` (the page bytes) and `GET /__apg/schema` (the IR rendered as JSON). | Three MACHINE rows, each three samples, conditions named (the fixture project's contract size, the rig on this machine, image cached): *launch to URL*, *page served*, *schema served*. Named what they are — server-side latencies a browser adds paint time to — and not called first paint. | Never write a measurement you did not run (D267); a number about a browser this workstation does not run would be exactly that. | D593, D603 |
| **D1259** | This plan's Run 1 step 3: write two audit rows *"with 0027's `agent_audit_begin`/`agent_audit_finish`"*. | **There is no `agent_audit_finish`.** 0027 drops and recreates `api.agent_audit_begin(text, uuid, jsonb, text, text)` and `api.agent_audit_complete(uuid, text, integer, integer, text)`; the second name is the one every caller and every proof uses. | The rigs and the Run 2 proof call `api.agent_audit_complete`. Named here rather than reconciled silently, because a plan that names a function the tree does not have is how a proof comes to be written against something nobody ran. | The tree wins. A wrong name in a runbook is cheap exactly once — on the day somebody greps for it. | — |
| **D1260** | Run 2's signature for the surface check: `surface_answer(ir, fetched: bytes | None, error: str | None) -> SurfaceAnswer`, and §1 D1253's *"`openapi_normalize.normalize` + `fingerprint`"*. | **`fingerprint()` does not normalize, and the committed snapshot is already in the neutral form** (`host: project.invalid:443`, `basePath: /__project_base_path__`). Measured in rig 24b: the raw served document fingerprints `f12cdc72c67f98e0…` against the snapshot's `808ac715c09aeebc…` — the same 16035 bytes, two different questions. `normalize` takes `expected_host` and `expected_base_path` as REQUIRED keyword arguments, derived by `bin/api-contract.py`'s `published_address()` from the deployed document's `routes.rest.url`, because ADR 0050 requires the real address to be validated before it is substituted. Control, measured: a wrong `expected_host` is refused (`NormalizationError`), not normalized into agreement. | **`surface_answer` takes the expected address**: `surface_answer(ir, fetched, error, *, expected_host, expected_base_path)`, both supplied by `address_book` from the same `routes.rest.url` the fetch used (ADR 0002 — derived once). A `NormalizationError` is `unreadable` with the normalizer's own reason, which is where a host mismatch surfaces. With the correct pair the equality holds: the served document to an APPLICATION-ISSUED human token normalizes to `808ac715c09aeebc…` and equals the committed snapshot **byte for byte** — rig 23a's equality, now through the app, which is the one thing it could not show. | A signature that cannot express the question is the defect, not the answer it would have produced. Had this been written as planned, Studio would have compared a raw document to a normalized snapshot and reported `stale_contract` against every correct deployment — green in no environment, but discovered in Run 4 rather than Run 1. | 0050, 0204 |
| **D1261** | D1254: the rig writes a deployed document naming loopback URLs, and Studio verifies the served surface against it. | **`normalize` refuses a document whose `schemes` is `['http']`** — *"A document offering http tells every generated client that cleartext is a supported way to reach this API"*. A rig whose `PGRST_OPENAPI_SERVER_PROXY_URI` is `http://127.0.0.1:<port>/api/rest` therefore serves a document Studio can only answer `unreadable` about (measured, arm B), even though the route is correct and reachable. | **The rig's proxy URI names the loopback host with the `https` scheme** — `https://127.0.0.1:<edge port>/api/rest` — while the deployed document's `routes.rest.url` stays `http://127.0.0.1:<edge port>/api/rest` and the transport stays cleartext loopback. Measured, arm C: `host` `127.0.0.1:32923`, `schemes` `['https']`, normalized fingerprint `808ac715c09aeebc…`, **equal** to the snapshot. The fixture's docstring says which value is the rig's and why (ADR 0065/0066). | The alternative is widening `normalize` to accept `http` for a loopback host, which would relax a released contract test so a rig could pass — the exact inversion runbook §6 forbids. The rig configures around it and says so. | 0050, 0065, 0066 |
| **D1262** | D1243 and §5 Run 1: record PostgREST's CORS header verbatim, *"it does by default in every version this project has measured"*. | **It does not.** Measured in rig 24b at the pinned image: `GET /notes` with `Origin: http://127.0.0.1:1` and a valid bearer answers **200** with `Connection, Content-Length, Content-Location, Content-Range, Content-Type, Date, Server` — **no `Access-Control-*` header of any kind**. | The threat model's *Studio* entry records what was measured, not what was expected: the upstream sends no CORS header, so a page that held a token could not read the answer it provoked anyway — and Studio's design makes the question moot for a second, independent reason (the page holds no token). Both sentences, because the second is the one that stays true when the first changes. | A premise wrong in the reassuring direction survives longest (D930); this one was wrong in the alarming direction, and repeating it would have put a measured falsehood in the threat model. | — |
| **D1263** | Run 1's close: *"`test_documentation_index` (the ADR index), then push. CI green expected (documentation only; the ADR index is generated content, so `bin/session-01-check.sh` alone is the rule — run it once, on the clean tree)"*. | **The ADR index is not generated content.** No generator writes `docs/decisions/README.md`: `git grep -ln "decisions/README" -- bin src tests` names three CONTRACT TESTS and no renderer (`test_documentation_index`, `test_acceptance_registry`, `test_repository_contract`). It is hand-maintained prose with three proofs over it, which is the *Documentation only* row of `CLAUDE.md` §5's table, not the *generated artefacts* one. And the gate could not have answered anyway: **WSL has lost outbound HTTPS again**, re-measured at this step rather than recalled — `urllib` to `pypi.org` fails immediately with `[Errno 101] Network is unreachable` (D1239 recorded a 20 s timeout; the same fact, a different failure mode), and `bin/lock-dev-deps.sh --check` resolves against PyPI by construction. | **The targeted list is the three modules that read the index**, derived from the tree and not from the plan's sentence (D1146, D1149): `test_documentation_index` 19 passed, `test_acceptance_registry` + `test_repository_contract` 256 passed, 40 s. No gate is run at this run's close. `bin/session-01-check.sh` is still owed at Run 6's close, where D1239's container workaround is the shape — and where there is code for it to check. | A gate run for a reason that turns out to be false is the same defect as a proof that never ran: nobody afterwards can say which question it answered. The grep names what the run CHANGES; the plan's list names what it ADDS. | — |
| **D1264** | Run 2 step 1: *“`test_migration_contract` green; a new proof in it, `test_0032_reissues_the_reader_grant`”*, and §2 lists the node id under `test_migration_contract.py`. | **There is no `test_migration_contract.py`.** The migration contract is `tests/contract/test_migrations.py` (480 lines: both dbmate blocks, no non-transactional apply, every down block refuses, every up block assumes and returns the owner role, the lock verifies, every granted function has a caller). The neighbours are `test_migration_ledger`, `test_rendered_migrations`, `test_api_migrations`, `test_output_migrations`, `test_project_migration_sets`. | `test_0032_reissues_the_reader_grant` is in **`test_migrations.py`**, beside the structural rules it belongs with, and §2's node id is written there when Run 6 reads the ids out of the tree (D1236). | A node id proposed against a module that does not exist is the registry defect D1236 is about, one file earlier. | — |
| **D1265** | Run 2 step 2: *“`openapi_docs.py`: the response schema gains `denial_reason` (nullable string…)”*, and *“the canonical document moves by exactly that member”*. Also: *“extend `ADMIN_SCOPES` in that module — grep every reader of that constant first”*. | **There is no response schema to widen.** `RESP_LIST_AUDIT`'s 200 is `openapi_docs.ok("Audit rows, most recent first.")` with no model, and the captured document carries `"schema": {}` for it — which is this file's shape for every LIST endpoint (`/admin/users`, `/admin/agents`, `/auth/jwks.json`); the four that declare a model are the single-object responses. **And the grep the plan asked for says not to touch `ADMIN_SCOPES`**: `test_the_audit_endpoint_needs_its_own_scope_not_the_agent_roster_one` asserts `"admin_audit:read" not in ADMIN_SCOPES`, so widening it would delete that proof to make a new one convenient. | The route serialises `denial_reason`; **the document moves by the endpoint's own description**, which now says a refused row carries the boundary and that a refusal recorded before the column existed carries null. Measured: `app-contract.sh --update` moves exactly one line of `app-openapi.canonical.json` and `--check` exits 0. No response model is invented — that is a layer for every list endpoint at once and this session did not price it. The new proof uses the module's own `_auditor`, and `ADMIN_SCOPES` is untouched. | A schema for one endpoint, added because a session needed a member documented, is a second shape in a file whose shape is a decision. The prose is where this document already says what a row carries. | 0050, 0142 |
| **D1266** | §9's stop condition: *“`classify_changes` returns nothing for the regenerated client while the app digest moved: a divergence row and a decision about the version rule, never a silent `1.0.0`”*. | **It happened, and it is correct behaviour.** `bin/apg.sh generate` printed *version 1.0.0 (no contract change)* while `app_openapi_sha256` moved `f21bf4a8…` → `e477fd23…`. `classify_changes` compares the **IR** — relations, RPCs, tools, enums, filter operators, auth — member by member (D1219), and not the digests; the IR did not move, because a description string is not an interface. ADR 0162's own class for it is `implementation`, which is a PATCH and which nothing feeds into the generator. | **The version rule stands, and the cost is named rather than fixed.** `clientVersion` is a claim about the client's INTERFACE, and `app_openapi_sha256` is provenance compared to nothing served (D1209, ADR 0204). The consequence, written down: two clients at the same `clientVersion` can carry different app provenance digests. Adding a digest term to `classify_changes` would bump every client for every prose edit to the application document, and is a change to a released rule that wants its own ADR and a session that is about the client. | The stop condition did its job: the answer was reached by reading `classify_changes` and `CHANGE_CLASSES` rather than by accepting a number. D1219 is the other half — the grain of this comparison has already been wrong once, in the permissive direction, and the repair was to make it finer rather than to add inputs. | 0162, 0204 |
| **D1267** | Run 2 step 5: `request_checks(*, host, bound, cookie, expected_cookie, origin, own_origin, method, custom_header) -> int | None`. | **Two of the five checks are about which path is being asked for**: `/open/<key>` is the one path that may arrive without the launch cookie (it is where the cookie is issued), and the custom header is required of `/__apg/` and of nothing else. The signature as written cannot express either, so the handler would have to decide which checks apply — which puts the policy back above the pure function and out of the battery's reach, the exact thing the split exists to prevent. | **`path` is a parameter.** The function takes `method, path, host, bound, cookie, expected_cookie, origin, own_origin, custom_header` and returns 405 / 421 / 403 / 401 / 403 or `None`. Fourteen inputs prove it, five refusals and five controls that differ by one field, plus a cookie parsed rather than substring-matched and an absent `Origin` served. Battery M3 and M4 killed. | The plan's signature was written before rig 24a measured which fields a handler actually sees; the rig's stub had the path in it from the first line. | **0205** |
| **D1268** | §1 D1243 and Run 3: *“`OPTIONS` is refused, so no cross-origin preflight ever succeeds”* — rig 24a measured `OPTIONS /__apg/x` → **405** against a handler that implemented it. | **`BaseHTTPRequestHandler` answers an unimplemented method itself, with 501 and none of this server's headers** — measured, on the first run of `test_options_is_refused_so_no_preflight_succeeds`: `501`, `Content-Type: text/html`, no Content-Security-Policy, no `Connection: close`. The refusal was the framework's, on the framework's terms, before `request_checks` was reached. Rig 24a could not have caught it: its stub bound `do_OPTIONS` to the same handler as every other verb, so the branch existed there and not in the product. | **`do_OPTIONS` exists and calls `refused()`**, which returns 405 with `SECURITY_HEADERS` and `Connection: close`; `do_PUT` and `do_DELETE` join it, so no method reaches the framework's 501. Battery M11 puts the defect back and the proof fails. | A rig that models the product's SHAPE can be right about the shape and silent about the default underneath it. The measurement said what happens when a handler implements the method; the product's question was what happens when it does not. | 0140, **0205** |
| **D1269** | §2 `STU-CMD-001`: *“argument errors exit 2 before any file is read”*, and Run 3's proof: *“a `--project` that does not exist with a malformed flag → 2, and the missing file is NOT what the message names”*. | **The wrapper checked each path as it parsed**, so `--project absent.yaml --nope` reported *file not found* and never reached `--nope`. Written that way because checking beside the flag is how the message comes to name the flag; the cost is that the FIRST path wins over every later shape error. | **Shape first, then the filesystem.** `bin/studio.sh` collects `(flag, path)` pairs while parsing and checks existence after the loop, so an unknown flag, a missing value and a positional argument all refuse before any file is opened — and the message still names the flag, because the pair carries it. Battery M12 puts the defect back and the proof fails. | An operator reading *file not found* goes looking for a path. The thing that was wrong was a word they typed. | — |
| **D1270** | Run 3's `test_every_response_carries_the_csp_and_security_headers`, written as: for every response, for every `name, value` in `studio.SECURITY_HEADERS`, assert the response carries it. | **It compared the product to itself.** Battery M6 deleted `X-Frame-Options` from `SECURITY_HEADERS` and the test **PASSED**: the mutation removed the header from the product and from the expectation in one edit, because they were one object. CLAUDE.md §7's sixth question — *who wrote the fixture, and do they share a belief with the code* — answered by a survivor. | **`EXPECTED_SECURITY_HEADERS` is written in the test module**, from ADR 0205 and §8, and the product's dict is compared to it as an EQUALITY in the same test — so a header added without review is as red as one removed. M6 re-run: killed. | The only thing that finds this class is a mutation, and the only thing that makes the mutation readable is a control it cannot reach. Three of this battery's twelve first came back with the control failing too, which is a broken PAIRING rather than a survivor, and each was re-paired rather than counted. | D499 |
| **D1271** | Run 3 adds a `bin/` command, and §5's rule is that the run adds it to `SHELL_COMMANDS`/`PYTHON_COMMANDS` and runs `test_cli_contract` (D1014, D1188). | **Two OTHER released guards caught it, and both were right.** (a) `test_no_command_documents_a_secret_argument` scans `--help` output for `--password` as a whole flag; the usage block said *“There is no --password flag”*, which is the opposite of documenting one and which a regular expression cannot read. (b) `test_no_operator_command_puts_a_service_directory_on_the_path` flags any `bin/*.py` holding both `"services"` and `sys.path` — the shape `bin/auth-admin.py` had when it made an image-only package importable in a checkout and nowhere else (D292). `bin/studio.py` names `services/studio` to READ three files, which is not that. | **Neither guard is touched.** (a) The help says the same thing without the spelling (*a password is never taken as a command-line argument*); the `--password)` case arm still refuses the flag BY NAME on stderr, which `--help` does not print. (b) `ASSET_ROOT` moves to `src/agentic_postgres/studio.py` beside `BIND_ADDRESS`, so the command holds no such literal — which is ADR 0002's rule anyway, and `services/studio/` is not a service: it builds no image and no deploy runs it. | A guard that fires on a file it was not written for is a prompt to move the file, not to teach the guard about negation. A scan that had to understand *there is no X* would pass the next command that documented one in a sentence. | 0002, D292 |
| **D1272** | Run 3: *“copy `generate.py`'s loading sequence, do not re-derive it”*. | A copy is a second authority unless something holds the two together (D486), and the better shape — extracting the sequence into the package so both commands call it — would rewrite a RELEASED command's error paths: `bin/generate.py`'s `fail()` exits with codes `apg studio` does not share, and every Session 23 proof drives them. | **Copied, and the pair is compared**: `test_the_ir_studio_builds_is_the_one_generate_wrote` asserts Studio's four digests, its relation names and its tool names equal the committed `generated.json`'s for the example project. A drift is then a red proof naming two commands rather than a UI quietly describing a contract the client does not. The extraction is §10's, priced at one module and one pass over `generate.py`'s exits. | A refactor of `apg generate` for the convenience of `apg studio` is a change to the wrong command, made in a session that is not about it. | 0002, D486 |
| **D1273** | §5: *“CI green on every commit that changes code”*, with Run 2 building `src/agentic_postgres/studio.py` and its unit proofs, and Run 3 building `bin/studio.py` — the module's only caller — one commit later. | **The two cannot both be true.** `test_repository_contract.py::test_no_module_is_imported_only_by_its_own_tests` refuses a package module whose only importers are its own tests: *“a module with no caller is a feature that does not exist, however well it is tested”* (D204). Run 2's commit is exactly that state, and CI said so — `34a3b28`, both jobs red on that ONE proof, `1 failed, 5507 passed` in the Session 1 gate and `1 failed, 5597 passed` in the Session 2 suite, nothing else in either. The workstation could not have seen it: the targeted list for a run that adds a module does not include `test_repository_contract`, and the guard is about the repository rather than about anything Run 2 touched. | **Recorded, not repaired by rewriting history.** Run 3's commit adds the caller and `test_repository_contract` passes in its targeted list (895 passed) — and **`deb4aa9`'s own CI is green**, read by full SHA, which is what makes this a reading of the split rather than a guess about it. The branch therefore has one red commit by construction, and the alternative — landing the pure core and its command in one commit — is what a future session should plan instead: the split is a reviewing convenience, and D204 is a property of the tree at each commit. | The guard is right and the plan was wrong, which is the direction this table exists for. A session that had “repaired” it by importing `studio` from somewhere to satisfy the scan would have built the feature the guard was written to prevent. | D204 |
| **D1274** | Run 4: *“**Capabilities** (the IR's tools: name, kind, arguments, scopes; the lock's `tools_sha256` and a fixed sentence)”* listed as one of six views, against Run 3's rule that *“under anything but ok the schema and query views are refused”*. | **Capabilities is not in either list, and Run 3 had already decided it by accident.** Run 3 built ONE endpoint for everything the IR carries, `/__apg/schema`, gated on `surface.answer == "ok"` — so the capabilities view would have been refused because a REST document disagreed. Those are two contracts: `tools_sha256` is compiled from the capability manifest and the reviewed surface, `rest_openapi_sha256` is the document PostgREST serves, and no launch answer is evidence about the first. The plan's own sentence for the view says as much — *whether the plane serves it is `bin/apg.sh doctor`'s question* — so it cannot be gated on a confirmation that was never about it. | **`/__apg/capabilities` is a second local endpoint, ungated**, served from `studio.capabilities_view(ir)` with `CAPABILITIES_NOTE` travelling in the payload rather than written into the page, so the data and its caveat cannot come apart. `forwarder_table()` is untouched: both endpoints are local and neither is an upstream request. `test_the_capabilities_view_is_served_whatever_the_surface_answered` runs both arms and asserts the two payloads are identical, with the schema view's 409 beside it as the control. | ADR 0195's folded third outcome, one level up: the answer was about one contract and would have been reported as though it were about another. | ADR 0195, D1201 |
| **D1275** | §5 Run 4: *“`test_launch_answers_ok_against_the_surface_the_ir_was_built_from`”*, with the fixture's one administrator holding every admin scope — and §5 Run 3's launch line, *“run `bin/apg.sh generate`”*, as the whole of what `stale_contract` says. | **The served REST document is scoped to the caller's grants, and the administrator's is empty.** Rig 24d, one URL and three tokens the auth application issued: `authenticated` is served 16,024 bytes, 8 paths and 3 definitions and fingerprints EQUAL to the committed snapshot; `project_admin` is served 2,393 bytes, **1 path and 0 definitions — byte for byte the same document as `anon`**, because the administrative role administers the auth service's endpoints and holds nothing in `api`. So an administrator's launch answers `stale_contract`, and the first run of the proof did exactly that. | **The answer is right and the sentence was wrong.** `stale_contract` means *the surface served to this subject is not the captured one*, which is the meaning Session 23's client already has — `test_init_refuses_a_surface_with_another_fingerprint_naming_both` produces it by changing only the token's role. What could not stand is a launch line offering ONE cause: an administrator told to regenerate would have regenerated a capture that was exactly right. `bin/studio.py`, `bin/studio.sh --help` and the page's detail line now name both causes. The `ok` proof launches as `alpha-user-a`, and `test_an_administrators_surface_is_the_one_their_grants_reach` is the administrator's half, with the `ok` launch beside it as the control. | The same shape as D1260, found the same way and one run later: a comparison that looked measured, against a document nobody had fetched as this subject. A session that had “fixed” the product to match the first run would have taught Studio to accept a surface it had not verified. | D1260, ADR 0204, rig 23a |
| **D1276** | Run 4's fixture, built from rig 24b, points the auth application at the dev cluster's PUBLISHED port — `127.0.0.1:<state.port>` — the way rig 24b did on this workstation. | **CI errored seventeen times, all at the fixture, all `PoolTimeout` behind `connection to server at "127.0.0.1", port 32782 failed: Connection refused` — while `docker exec psql` against the SAME container in the SAME fixture had succeeded twice, seconds earlier.** So the cluster was running and its published port was not reachable from the runner's own loopback. `apg dev up` publishes `-p 127.0.0.1:0:5432` by decision (D1175, rig 22a): the port exists on loopback and nowhere else, which is right for a developer's machine and depends on a host-to-loopback DNAT a daemon can be configured not to make. Every other cluster this suite starts publishes on all interfaces, which is why no other rig had met this. | **The fixture proves an address before it builds on one.** `cluster_address()` tries the published port, falls back to the container's own address read from `docker inspect`, fails with a message naming both and what `docker exec` could do, and returns WHICH answered — recorded in the rig and warned about when it is not the first. Not a switch on the machine's name: the question is *can this process reach it*, and only a connection answers that. | CLAUDE.md's own rule in a new place: read the container, not the file. `state["port"]` is a true record of what `up` published and says nothing about whether anything can reach it — a value that looked measured and was not. **A second CI round-trip was needed and the mechanism is still unestablished**: the probe answered and the pool was refused at the same port, so the probe moved to AFTER the rig's network is joined, and `f26e600` is green — with the fallback never firing, which means the published port worked there. That rules OUT the proposed mechanism (joining a network costing the mapping) and establishes only that the reading has to be taken in the topology the rig will use. Reported rather than resolved (ADR 0195). | D1175, D1152, ADR 0195 |
| **D1277** | Run 5: *“a **Studio** entry under *Threats*”*, *“the status paragraph at Session 24 … write the prose now with `1.5.0` and let Run 6's guard confirm”*, and *“§1's numbers **counted, not recalled**”*. | **Three of the five document edits are guarded against constants Run 6 moves, and writing them here leaves a commit its own guards refuse.** The threat table's two acceptance columns are parsed and must name requirements present in `tests/acceptance-registry.yaml`; every registered requirement belongs to a claim (D697); the `STU-*` family and its claims are Run 6's. `test_the_readme_states_the_session_the_release_implements` compares the README's *Session N implemented* to `CURRENT_SESSION` — writing 24 here failed it on the spot — and `test_the_readme_quotes_the_release_it_ships` compares `template_version` to `VERSION`. And §1 is *the position*, which the registry changes in Run 6, so counting it now publishes numbers a later commit in the same session makes wrong (D1194). | **Each moves to the run that moves its constant, and everything that does not depend on one lands here.** The threat model gets the whole Studio ANALYSIS — the hostile page, the five checks, rig 24b's measured CORS answer, the local-process residual — which the parser does not read; the table ROW lands in Run 6 with its requirements. The README gets Studio's own section and a sentence saying the session is built and not yet a release, with the status line unchanged. The ledger gets §13 whole; §1 is counted in Run 6. | **D1273, applied forward rather than repeated.** Last run recorded a commit that was red by construction and said a future session should land a module with its caller together. Doing the same thing deliberately one run after writing that down would be worse than the original. | D1273, D936, D1194, D697 |
| **D1278** | Run 6 step 3: the live module marked `requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_ADMIN_PASSWORD_FILE")`. | **`tests/conftest.py::ENVIRONMENT_VARIABLES` is a CLOSED tuple and does not carry the third name.** `apply_environment_gate` raises `pytest.UsageError` on any name outside it, deliberately: *“a typo here would produce a test that silently never runs”* (D687). Every existing module that needs the administrator's password file reads it through the `admin_password` fixture, which fails naming the variable when it is unset — and §2 of this plan says the same thing in the sentence beside it (*“the live module READS”*), so the two halves of the plan disagree rather than the plan and the tree. | **Gated on the two declarations that are declared.** The third is read by `admin_password` the way every other module reads it. Widening a closed roster is a decision about the roster, and this run had no reason of its own to take it. | The guard is right and one sentence of the plan was wrong about it — and the OTHER sentence of the plan was right, which is the useful part: the brief contained its own correction. | D687 |
| **D1279** | Run 6 step 5: *“a derivation script whose every substitution is anchored to match exactly once”*, with the header and usage *“rewritten whole and read line by line, both halves”*. | **Nine anchored substitutions left four header blocks standing, and one of them had become FALSE.** The precondition an operator reads before a host trip said *“Both projects deployed `--through-session 23`, which publishes outputs v18 — unchanged, because Session 23 moves no outputs schema and adds NO released migration”*. Session 24 adds migration 0032, so an operator reading it would have expected a deploy that applies nothing and then found each ledger one row longer. The other three named the wrong session's claims, the wrong previous gate and the wrong count of runtime rigs. | **All four rewritten, and the line-by-line read is what found them** — a substitution can only repair text somebody predicted would differ. The derivation script prints every line of its output still carrying a `23` so the read has somewhere to start; twenty-four remain and every one is a true reference to what Session 23 did. | D505's family, which is why the plan asked for the read. What is new is the KIND: not a stale name but a stale FACT — and the fact is a precondition for an irreversible operation. | D505, D853, D858 |
| **D1280** | Run 6 step 5: *“`tests/contract/test_session_twenty_four_gate_modes.py` derived from 23's”*. | **The derivation repaired the script and left three literals in the module that guards it, and one of them is a defect rather than a staleness.** `test_the_gate_exists_and_is_executable_in_the_git_index` ran `git ls-files --stage -- bin/session-23-check.sh`: it would have asserted the PREVIOUS gate's mode bit, and a new gate committed without one would have passed it. The merge-help test looked for `session-23-offline.json` while the gate DERIVES that filename from `${SESSION}` with `%02d`. And the staleness guard looked for `session-21-check` — two gates back, inherited from Session 23's own derivation, **passing for free ever since**. | **Every one derived from `SESSION` or from `SCRIPT`.** A literal that cannot be left behind is the only fix that survives the next derivation. The corrected executable-bit test then went red immediately on the real thing: the new gate was not yet in the index (D1188). | The guard against a stale derivation was itself stale, in the module whose subject is stale derivations. Session 23's copy still carries its own version of two of these and is left as it is — an open item rather than an edit to a released module this run had no other reason to touch. | D505, D703, D1188 |
| **D1281** | Run 6 step 5: the per-session offline assertion, *“D1237: assert THIS session's two are in the set; never assert the set's size”*. | **D1237's own repair was one scope too wide, and the third offline session is where it shows.** Session 22 asserted an equality against the whole of `OFFLINE_CLAIMS`, which became *no later session may declare an offline claim* — caught by Session 23 (D1237). Session 23's replacement was a SUBTRACTION: `OFFLINE_CLAIMS` less every claim an EARLIER session introduced. That is right for exactly as long as no LATER session declares one. Session 24 declares two, and Session 23's module failed with this session's names in its own `mine` set. | **Matched on the session, in both modules**: the claims whose `CLAIM_INTRODUCED_IN` entry equals that module's own `SESSION`. Each module then owns its own two names, which is what both docstrings already said they wanted. Nothing is lost — under the subtraction a stray later declaration reddened an EARLIER session's module, which is the wrong place and blocks every later offline session by construction. | **The same defect twice, one turn apart, inside the repair for the first instance.** An assertion stated one scope too wide reads as correct until the case beyond its scope exists, and the repair inherited the habit of describing the property in terms of everything ELSE. | D1237 |
| **D1282** | Run 7 step 7: the one sweep runs *"with every declaration `--help` lists — the five Session 18 flags with a **FRESH kit** exported first (`bin/dr-kit.sh export`, *(sudo 8b)*, then `verify` from this checkout off-host: **REC-KIT-003** as a reading)"*. | **REC-KIT-003 refuses a fresh kit, by construction, and `pytest.fail`s rather than skipping.** `test_the_kit_exported_before_this_release_verifies_at_it` reads every stored deployed document in `--kit-dir`, keeps those BELOW `output_migrations.CURRENT_VERSION`, and fails with *"every stored document … is already at outputs v18; point --kit-dir at the kit exported BEFORE the deploy through this session (the premise of REC-KIT-003)"* when none is older. The claim IS the version gap. Measured on the host, offline: `kit-2026-09-06` stores v16, `kit-2026-09-11` stores **v17**, the tree renders **v18**, and Session 24 moves no outputs version — so the existing kit is exactly the premise and a kit exported today is exactly its negation. REC-KIT-001 is version-agnostic (it verifies and scans for this host's values), so one flag serves two claims whose premises point opposite ways and the OLDER kit satisfies both. | **The sweep gets `--kit-dir /home/op/kit-2026-09-11`**, and `g24-host.sh` says in its header why the old kit is the right one. The fresh export stays on the sheet as the OPERATIONAL obligation it is (`CLAUDE.md` §2: the kit is stale after the next deploy — re-export and copy off), verified off-host with `bin/dr-kit.sh verify`, and is **not** passed to the gate. | A sentence that reads like hygiene — *export a fresh kit first* — would have turned a claim that has passed twice into `failed` and exited the gate 5, on the one sweep the trip pays for. Found by reading the proof the plan named instead of the flag it named. | D1122, D1141, 0189 |
| **D1283** | Run 7 step 8: *"**Measure first**, on the 22 merge, that the writer ACCEPTS a host half written by the Session 24 gate for `--session 22`"* — with a fallback (re-deriving each half by re-invoking the writer's half-writing step with the session number changed) and *"the D row records which of the two it was"*. | **It accepts, and the measurement did not need the host.** Run offline with Session 21's host half and `--session 22`: the writer got past the session number entirely — `merged = {**host, **external, "session": session, …}` takes `session` from the ARGUMENT, and a half's own `session` field (21, here) is never compared to it. It then failed for the two honest reasons: the offline half named a different checkout, and 22's claims were absent from a Session 21 sweep. **The commit difference is PRINTED and not fatal** — `offline_checkout_commit` is recorded beside `source_commit` and the run continues (ADR 0202 §3); the writer's one `return 5` is *"neither half recorded these claims"*, which is the real check. And the third merge needs only ONE `--offline-input`: Session 23's own offline half carries all **six** offline claims, 22's four included, so 24's carries all eight. | **The fallback is not needed and is not run.** The three merges are the plan's three commands unchanged, and the expected stderr line on the 22 and 23 merges — the offline half at `8823877e` / `2121c029` against a deployment at this session's release — is the difference D1244 already priced, printed rather than hidden. | The plan asked for a measurement and named the branch it would take either way, which is why this cost one command instead of a decision on the day. The answer is also the less obvious one: nothing ties a half to the session whose gate wrote it, and the merge is honest because the CLAIM SET is checked, not the filename. | D1244, 0202, 0195 |
| **D1284** | `tests/contract/rendered_fixtures.py`: three states, and *"stale — rendered at a version the code has left — FAIL, and say the gap"*; the docstring names the one thing the `schema_version` proxy does not catch (a `compose.env` missing a key) and closes *"a check whose name is wider than its evidence is this repository's standing defect"*. | **There is a second blind spot, and Session 24 is the first session in several to produce it: a RELEASED MIGRATION added with no outputs migration beside it.** The pre-trip offline gate went red on one P0 proof — `test_a_project_without_a_set_records_exactly_the_releases_migrations`, `assert 31 == 32` — while CI was green at the same commit and the module passed alone. Not ordering: the JUnit records execution order and it is CI's. **Proved with a control pair**: the same directory rendered from `4af67ca` (the commit before `0032`) gives outputs **v18**, 31 rendered migrations, the check answers **`current`**, and the ledger proof fails with exactly the sweep's assertion; rendered from the tree it gives v18, 32, `current`, five passes. So the fixture was a release behind and the check called it current — **wrong in the reassuring direction** (D930, D957), and invisible to CI, which has no `.generated/` to be stale. **And not local**: the host's `.generated/` is Session 21's — v18, 31 migrations — so `g24-offline.sh` would have failed the same way on the day. | **One measurement added, not a new mechanism.** `_state()` now compares each fixture's rendered RELEASE entries to `migrations.release_set()`'s, by version, in order, and reports the gap the way the version gap is reported: *"fixture-alpine-dev's release set is 31 rendered against 32 released; absent from the render: 20260912120032 — re-render: ./deploy.sh --render-only"*. Two proofs: a behavioural one that builds the drift in `tmp_path` with the untouched pair as its control, and a wiring one so adding `0033` needs no edit. Battery 3/3, control green throughout. The docstring says what is still not caught and why (a project set needs a manifest, and a currency check that loads manifests is a second renderer). `s24-renders.sh` runs before `g24-offline.sh` on the host, and now asserts rather than assumes it. | The module was honest about being narrow and named the blind spot it had thought of; the one it had not was the one a session adding a migration would hit. **A gate step called "Rendered fixtures are current" that answers `current` is worth less than one that says `I compared the version only`** — and the difference showed up as a P0 red with no explanation in it, three hours before a host trip. | D212, D930, D957, 0073, 0198 |
| **D1285** | `bin/dev.py::container_state`: *"`docker inspect`'s word for this container, or `None` if it cannot say"*, deciding between the two on `"No such object" not in probe.stderr`; and `dev_environment.status_of`'s docstring, *"four outcomes and not three, because 'there is no environment' and 'there is an environment and I could not ask it anything' are different facts and a developer acts differently on each (ADR 0195)"*. | **The distinction was never made, because the substring is capitalised and docker's is not.** Measured at the pinned daemon with a control: an absent container gives **exit 1** and stderr `error: no such object: <name>` — **lower case**, no capitalised match — while an existing one gives exit 0, stdout `running`, empty stderr. So `container_state` returned `None` for every absent container, and `apg dev status` printed *"state records container X, and docker could not be asked about it; **is the daemon running?**"* while the daemon was answering every other call in the same process. **ADR 0195's class inverted**: not a reader folding *I could not determine it* into an answer, but a reader that HAD the answer and reported that it had not — with a remedy attached that sends the developer to the wrong thing entirely. **And `container_state` had no proof at all**: `grep -rn container_state tests/` returned nothing, so the one branch separating the two outcomes had never run in any environment. Found because the gate's second run hit it for real — my own cleanup had removed a container the killed run's state still recorded — and the exit code cannot stand in for the wording, since `inspect` exits 1 for an absent object and an unreachable daemon alike. A comment in `test_session5_api_contract.py` has recorded the lower-case spelling since Session 5 (D195), one grep away the whole time. | **`ABSENT_PHRASES` is a named constant matched case-insensitively against a lower-cased stderr, and both spellings are in it** — `inspect` says *object*, the typed verbs say *container*, and neither is a contract. Three proofs where there were none, and the PAIR is what makes them mean anything: one asserts a definite *no such thing* reads as `absent`, one asserts an unreachable daemon reads as `None`, and either alone is satisfied by a conflation. Battery 3/3, first pass — mutation 1 restores the defect and kills only the `absent` proof, mutation 2 returns `absent` for every failure and kills only the unreachable one. Neither proof starts a container, so the module's standing rule holds. | **The single reader nobody had ever tested, in the function whose docstring is about telling two silences apart.** Session 22 wrote the four-outcome design and the ADR 0195 reasoning correctly and then compared against a string it had not measured — question 3 of §7, asked of a third party rather than of an identity. The trip merges `apg dev`'s own claims, so shipping this while writing Session 22's evidence would have been the wrong order. | 0195, 0203, D195, D267 |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

Family `STU-*` (new; joins `ID_PATTERN` in
`tests/contract/test_acceptance_registry.py` beside `DEV` and `GEN` with its
reason — *a STUDIO surface: what the product shows a human on their own
machine, holding only what that human holds*), `AGT-*` extended by one. All
P0, `target_session: 24`. Every requirement belongs to a claim (D697); a new
requirement gets a claim of its own and is never joined into an older one
(D1150, ADR 0089). Node ids are proposed; **Run 6 writes what the runs
actually wrote, read out of the tree** (D1236: two clauses of a Session 23
requirement had no proof; check every clause below against a node id).

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `STU-BIND-001` | `apg studio` listens on `127.0.0.1` and on no other address; no flag or setting binds elsewhere; the printed URL carries a per-launch key; a request without the launch cookie is 401, with a `Host` other than the bound address 421, with a foreign `Origin` 403, an `OPTIONS` 405, a forwarded call without `X-Apg-Studio` 403 — each with its passing control | `test_studio_server.py::test_the_listener_is_on_loopback_and_nowhere_else`, `::test_there_is_no_bind_flag_and_the_address_is_a_constant`, `::test_a_request_without_the_launch_cookie_is_refused`, `::test_a_foreign_host_header_is_refused_as_misdirected`, `::test_a_foreign_origin_is_refused_and_the_own_origin_passes`, `::test_options_is_refused_so_no_preflight_succeeds`, `::test_a_forwarded_call_needs_the_custom_header` | — (offline claim) |
| `STU-TOKEN-001` | Studio holds the human's access and refresh tokens in process memory and nothing else — no signing key, no database credential, no provider token, no SSH key; the password comes from a TTY prompt or a 0600 file and is refused as an argument or an environment variable; the token never reaches the page (no response body, header or asset contains it), is never printed and never logged; Studio verifies no JWT (imports no `jwt`/`jwks`/`cryptography`; a refused token is relayed as `refused`, never as the upstream body) | `test_studio_command.py::test_a_password_argument_or_environment_variable_is_refused`, `::test_the_password_file_must_be_owner_read_only`, `test_studio_runtime.py::test_no_page_response_header_or_asset_carries_the_token`, `::test_nothing_studio_prints_is_a_token_a_key_or_a_value`, `test_studio_server.py::test_studio_holds_no_key_and_verifies_nothing`, `::test_an_upstream_refusal_is_classified_and_its_body_is_not_relayed` | — |
| `STU-SURFACE-001` | At launch Studio fetches the served REST document as the human, normalizes and fingerprints it with `openapi_normalize`, and compares to the IR's digest: `ok`, `stale_contract` naming both digests and the regenerate command, `unreachable`, `unreadable` — four answers; on anything but `ok` the schema and query views are refused and the application views remain; the schema browser renders the IR's relations, columns, types, enums and RPCs and nothing the IR does not carry | `test_studio_runtime.py::test_launch_answers_ok_against_the_surface_the_ir_was_built_from`, `::test_launch_answers_stale_contract_naming_both_digests_and_refuses_the_rest_views`, `::test_unreachable_and_unreadable_are_two_answers`, `test_studio_core.py::test_the_schema_view_is_the_ir_and_nothing_else` | — |
| `STU-QUERY-001` | The query builder sends structure and the process builds one PostgREST `GET`: a relation, columns and operators outside the IR/capability schema are refused before any request; `limit` is bounded by a named constant; a value is a value (URL-encoded; `,`/`.`/`(`/`)` never syntax); no operation in the forwarder's table writes to the REST route; through Studio as user A the rows are A's and none of B's | `test_studio_core.py::test_rest_query_refuses_a_relation_a_column_or_an_operator_the_surface_does_not_name`, `::test_rest_query_bounds_limit_and_names_the_constant`, `::test_a_value_is_encoded_as_a_value_and_never_as_syntax`, `::test_the_forwarder_table_has_no_rest_write`, `test_studio_runtime.py::test_a_query_as_a_returns_as_rows_and_none_of_bs`, `::test_a_query_syntax_value_finds_nothing_and_the_stored_value_is_found` | — |
| `STU-AUDIT-001` | The audit view fetches `GET /admin/audit?limit=500` (plus `agent_id`/`owner_id` when chosen) and renders every row of the page — the denial boundary included — with the page's own count beside any view filter (*n of m on this page*); the page's row count equals the newest-500 count over the table as root; a token without `admin_audit:read` sees the endpoint's refusal, classified | `test_studio_runtime.py::test_the_audit_view_renders_every_row_of_the_page_with_its_boundary`, `::test_the_audit_page_count_equals_the_tables_newest_rows`, `::test_a_view_filter_hides_no_row_from_the_pages_count`, `::test_a_token_without_the_audit_scope_is_refused_and_classified` | — |
| `STU-REVOKE-001` | Revocation is `PATCH /admin/agents/{id}` `{status: revoked}` through the forwarder, refused with 422 and the shell's message when `confirm != agent_id`, before any upstream request; after it the agent's secret exchange is refused and `agent_claims_are_current` returns NULL; live: the agent's next MCP request is refused and the refusal's row is visible in the viewer | `test_studio_core.py::test_revoke_refuses_a_confirmation_that_is_not_the_agent_id_before_any_request`, `test_studio_runtime.py::test_revocation_through_studio_stops_the_agents_next_exchange` | `test_session24_studio.py::test_revocation_through_studio_refuses_the_agents_next_request_on_alpha` |
| `STU-SESSION-001` | Studio refreshes its token before expiry through `/auth/refresh`; it ends the session it began at exit through `DELETE /auth/sessions/{id}`; when its own session cannot be determined it ends none and says so | `test_studio_runtime.py::test_studio_ends_the_session_it_began`, `::test_studio_refreshes_before_expiry`, `test_studio_core.py::test_an_undetermined_own_session_is_reported_and_none_is_ended` | — |
| `STU-SUPPLY-001` | `services/studio/` holds three first-party files and no third-party code: no `package*.json`, no external URL, no inline script; the server sends the CSP and security headers named in §8; the Python is standard library plus `agentic_postgres` (HOST_PACKAGES) | `test_studio_assets.py::test_studio_assets_carry_no_third_party_code`, `::test_the_page_carries_no_inline_script_and_no_external_reference`, `test_studio_server.py::test_every_response_carries_the_csp_and_security_headers`, `test_operator_commands_run_on_the_host.py` (existing; `bin/studio.py` joins its list by construction) | — |
| `STU-CMD-001` | `bin/studio.sh` is a verb of the dispatcher; argument errors exit 2 before any file is read; an unrendered project is refused with exit 4 naming the render command; a deployed document with no ready REST or app route exits 5; an `http` route to a non-loopback host exits 5; a login refusal exits 6 and says only that the credential was refused; nothing printed is a credential; `--help` names the four surface answers | `test_studio_command.py::test_studio_is_a_verb_of_the_dispatcher`, `::test_argument_errors_exit_two_before_anything_is_read`, `::test_an_unrendered_project_is_refused_with_exit_four_and_the_render_command`, `::test_a_document_without_a_ready_route_exits_five`, `::test_an_http_route_to_a_non_loopback_host_is_refused`, `::test_a_refused_login_exits_six_and_says_no_more`, `::test_help_names_the_four_surface_answers`, `test_cli_contract.py::test_commands_are_executable_in_the_git_index` | — |
| `STU-ENV-001` | The capacity envelope carries three MACHINE rows for Studio — launch-to-URL, the page served, the schema served — with the machine, the fixture's contract size and the cache state as conditions; the document is current | `test_capacity_envelope.py::test_the_envelope_carries_studios_three_latencies`, `::test_the_envelope_is_current` | — |
| `AGT-AUDIT-002` | `auth_list_agent_audit` returns `denial_reason`; `GET /admin/audit` serialises it; it is non-null exactly on `refused` rows; the arity stays `(uuid, uuid, integer)`; the grant to the auth service is re-issued by 0032; live: after a real refusal on alpha the endpoint's row for it carries the boundary the plane recorded | `test_agent_audit_plane.py::test_the_audit_read_returns_the_boundary_exactly_on_refused_rows`, `test_auth_endpoints.py::test_admin_audit_serialises_the_denial_boundary`, `test_database_function_signatures.py` (existing; run by name — D1240's four unswept modules include it), `test_migration_contract.py::test_0032_reissues_the_reader_grant` | `test_session24_studio.py::test_the_deployed_audit_read_carries_the_boundary_of_a_real_refusal` |

**Claims** (`src/agentic_postgres/evidence_claims.py`), each dated 24:
`studio_boundary: ("STU-BIND-001", "STU-TOKEN-001", "STU-SUPPLY-001", "STU-CMD-001")`
and `studio_surface: ("STU-SURFACE-001", "STU-QUERY-001", "STU-AUDIT-001",
"STU-SESSION-001", "STU-ENV-001")` — both in `OFFLINE_CLAIMS` (every proof
runs in a checkout against rig 24b or against the source; Docker required; a
skip is not a pass). `studio_revocation: ("STU-REVOKE-001",)` and
`audit_boundary_reported: ("AGT-AUDIT-002",)` are **host** claims, not
declared offline: each has a live proof on alpha, because a revocation is
about a running plane refusing the next request, and a boundary is about a
refusal the deployed plane actually recorded. **The `OFFLINE_CLAIMS` test is
per-session** (D1237: assert THIS session's two are in the set; never assert
the set's size).

**No new gate variable.** The live module reads `APG_LIVE_HOST`,
`APG_PROJECT_A_OUTPUTS` and `APG_ADMIN_PASSWORD_FILE` (the alpha
administrator creates the audit-capable subject the way `audit_admin` does,
and the agent the way `create_reader` does). Studio is launched by the proof
with `--username <that subject> --password-file <a 0600 file the proof
wrote>` — the credential is the proof's own subject's, made through the
product's endpoints (D298).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| Migration `0032` released | Run 2 | Fix-forward only (D912); DROP + CREATE of a `STABLE SECURITY DEFINER` function with the same arity; the grant re-issued in the same file; `freeze-lock`; proved against a cluster that has rows written by 0027's functions (D940: history) |
| `app-openapi.canonical.json` recaptured; the example client regenerated | Run 2 | `app-contract.sh --check` and `generate --check` both green in the same commit (D1238); the client's `clientVersion` moves by the version rule and the diff is the review |
| `services/studio/` and `bin/studio.*` | Run 3 | Listed in `test_repository_contract.py`'s tracked-file list; `chmod 755` on the two commands before `git add`; `SHELL_COMMANDS`/`PYTHON_COMMANDS` gain them the run they land (D1188) |
| `CURRENT_SESSION` 23 → 24 | Run 6 | All-or-nothing (D690); every `target_session: 24` requirement's proofs in the same commit; the live module collected under `--setup-plan` with the variables set |
| `VERSION` 1.4.0 → 1.5.0 | Run 6 | Proposed minor (`migration_added`, a new command, an additive response field); Run 7's `upgrade plan` confirms or stops; the client regenerated in the same commit (D1238) |
| Deploy `--through-session 24` on alpha and beta | Run 7 | `upgrade plan` OK first; alpha first (the control that declares no set); ledgers read after (D941): alpha 32, beta 34; auth/mcp recreated on both (ADR 0155); the doctor 10/10 |
| Agents created, revoked and swept on alpha by the live proof | Run 7 | The proof's own names, swept in `finally`; the audit rows stay (append-only, by design) |
| DR kit re-exported | Run 7 | `bin/dr-kit.sh export` as `g18-host3.sh` does; copied off; `verify` from this checkout |
| Merge of `session-24` into `main` | Run 7 | Fast-forward only after CI is green on the branch's last commit |

Not irreversible and worth saying: rig 24b removes every container with
`docker rm -f -v` and runs `apg dev down` in `finally`; Studio's process ends
its own session at exit; every Studio run in a test is a subprocess killed in
`finally` and its stderr kept for the scan.

---

## 5. Build order, run by run

Each run ends with: ruff (its **exit code** printed), the targeted modules
(named, each checked for existence individually — D1104), derived documents
regenerated where a generator's input moved, `chmod 755 bin/*.sh bin/*.py
deploy.sh`, one commit on `session-24` with a message file, a push, and
**that commit's CI verdict read** by full SHA with three buckets (D1059). A
run that writes a test runs its battery (appendix). Mark the run **Done.**
with what it measured. **A targeted list is derived from the tree** (D1146,
D1149, D1184, D1187): a run that moves a definition greps every reader of the
name AND of the distinctive text and runs every module found, whole. A red
CI on the branch is a stop condition.

**Docker is required for Runs 1, 2, 3, 4, 5 and 6** (the rigs, the cluster
proofs, the runtime module, the gate). If `docker version` fails in WSL, stop
and say so; do not write a proof that skips. **No network is required by any
run** — Studio adds no package (D1249) — and Run 7 needs SSH to the host.

### Run 1 — the measurements and ADR 0205

**Read first:** this plan's §0 and §1 whole; `tests/contract/
test_generated_client_runtime.py` lines 1–430 (the rig this run extends);
`tests/contract/test_auth_endpoints.py` lines 116–420 (`cluster`,
`signing_key`, `administrator`, `environment`, `drive` — how the auth app is
configured and started against a dev cluster); `services/docs/serve.py`
whole; `compose.yaml` lines 700–770 (the PostgREST block, `PGRST_JWT_SECRET:
"@/etc/postgrest/jwks.json"`); `bin/render-jwks.py` (how a JWKS is derived
from a signing key); `services/auth-api/app/routes.py` lines 425–540 and
940–1050; `migrations/templates/0020-agent-audit-reader.sql` and
`0027-agent-audit-denial-taxonomy.sql` whole; Session 22's plan §5 Run 1 (the
shape of a planning-measurement run and its Done paragraph).

Rigs are throwaway scripts under `/tmp` in WSL (copied to the scratchpad
before any `wsl --shutdown`), each with a control arm, output to a `.txt`
file, numbers pasted into the Done paragraph. **Nothing under `src/`, `bin/`
or `tests/` changes in this run except the ADR and its index line.**

1. **Rig 24a — the loopback server and its four refusals.** A 60-line Python
   script: `ThreadingHTTPServer(("127.0.0.1", 0), Handler)` in a thread;
   print `server_address`; `ss -ltn` (or `socket` probing `0.0.0.0:PORT` and
   `127.0.0.1:PORT` when `ss` is absent — record which); the CONTROL: the
   same class bound to `("0.0.0.0", 0)` and the same reading. Then with
   `urllib.request` against the loopback one: (a) `GET /` no cookie → expect
   401; (b) `GET /open/<key>` → `Set-Cookie` with `HttpOnly; SameSite=Strict;
   Path=/` and a 303 to `/`; (c) `GET /` with the cookie → 200; (d) the same
   with `Host: evil.example:PORT` → 421; (e) with `Origin:
   http://attacker.example` → 403 and with `Origin: http://127.0.0.1:PORT` →
   200; (f) `OPTIONS /__apg/x` → 405; (g) `POST /__apg/x` with cookie but no
   `X-Apg-Studio` → 403, with it → whatever the stub answers (200). Record
   every status. **What this measures:** that `http.server` exposes `Host`,
   `Origin` and `Cookie` as the handler sees them and that a 421/403/405 can
   be sent before any body is read (`self.rfile` untouched — measure that a
   refused POST with a body does not hang the connection: send one with
   `Content-Length: 1000000` and a 1 s timeout).
2. **Rig 24b — the served surface WITH the auth application, published on
   loopback.** Start from `served`'s exact sequence (copy the fixture body
   into `/tmp/r24b.py`, `sys.path.insert(0, ".../src")`): `apg dev up` on the
   fixture project, the authenticator role's password, PostgREST from
   `postgrest_environment(...)`, Traefik stripping the prefix — **and publish
   the edge with `-p 127.0.0.1:0:8080`**, reading the port with `docker port
   <edge> 8080` (D1172's form). Then the auth app: generate an RSA key as
   `signing_key` does; build `environment` as `test_auth_endpoints.environment`
   does (read that fixture line by line — it names every `APG_AUTH_*` variable
   the app needs and where each value comes from in the rendered document);
   start `uvicorn` on `127.0.0.1:0` in a thread (`uvicorn.Config(app,
   host="127.0.0.1", port=0)`; `uvicorn.Server.run` in `threading.Thread`;
   read the bound port from `server.servers[0].sockets[0].getsockname()` —
   measure that this attribute exists at the pinned uvicorn, and record the
   alternative if not: bind a socket yourself and pass `fd=`). Render the
   app's JWKS (`GET /auth/jwks.json`) to a file and start PostgREST with
   `PGRST_JWT_SECRET=@/etc/postgrest/jwks.json` mounted 0644 (the compose form)
   — CONTROL: the HS secret form `served` uses, to show both work at the
   pinned PostgREST. Create one administrator as `administrator` does and TWO
   users through `POST /admin/users` (A and B, `authenticated`, `notes:read`),
   `POST /auth/login` for each, and: `GET <edge>/api/rest/` as A with
   `Accept: application/openapi+json` → normalize → fingerprint **==** the
   fixture snapshot's (rig 23a's equality, now through the app-issued token
   — the one thing rig 23a could not show); insert two notes as A and one as
   B through PostgREST as each; `GET /notes` as A → 2 rows, as B → 1, and as
   A with `owner_id=eq.<B>` → 0 (RLS, the client fixtures' third assertion).
   Then `GET /auth/sessions` as A: exactly one live row; note `created_at`
   resolution (D1252's "same instant" case: log in twice as A within one
   second and read whether `created_at` differs — record the resolution).
   Then: `Origin: http://127.0.0.1:1` on a `GET <edge>/api/rest/notes` →
   record whether PostgREST answers `Access-Control-Allow-Origin` (it does by
   default in every version this project has measured — record the header
   verbatim; it is the fact D1243's forwarder makes irrelevant, and the
   threat model's §*Studio* names it). Timings: `apg dev up` to auth ready.
   **Tear down in `finally`**, then `docker ps -a | grep apg-` must be empty.
3. **Rig 24c — the audit reader and 0032, on the same cluster** (before
   teardown, or a second `apg dev up`): as the migration user, run
   `SELECT proname, pg_get_function_result(oid) FROM pg_proc WHERE proname =
   'auth_list_agent_audit'` → the RETURNS TABLE without `denial_reason`
   (D1247 measured). Write two audit rows with 0027's `agent_audit_begin`/
   `agent_audit_finish` as the tests in `test_agent_audit_plane.py` do — one
   `served`, one `refused` with `denial_reason = 'scope'` (read the enum's
   members from 0027 lines 44–54 and use the first). Draft
   `/tmp/0032.sql` exactly as §1 D1247 specifies (DROP, CREATE with the
   column appended, COMMENT, REVOKE FROM PUBLIC, GRANT TO the auth service
   role — substitute the rendered role names by hand for the rig), apply it
   as the migration user in one transaction, and read the two rows back
   through the function AS THE AUTH SERVICE ROLE (`SET ROLE`): the refused
   row carries `scope`, the served row `NULL`. CONTROL: before 0032 the same
   `SELECT` has no such column (an error naming the column). Arity: `SELECT
   pronargs` before and after → 3 and 3.
4. **ADR 0205** — *Studio is a same-origin forwarder that holds the human's
   token and binds loopback with no alternative*: context (D1243, D1245,
   D1246, D1249, D1254), the decision (the process holds the token; the page
   holds a launch cookie; the forwarder's table; no bind flag; no third-party
   code; the loopback-`http` exception with its reason; the four launch
   answers copied from ADR 0204), the alternatives refused (token in the
   page + CORS; a container; a bundle; a SQL box with an allowlist — which
   is a SQL box), what it costs (the rig's ~3 minutes in every offline sweep;
   a human who wants Studio on a LAN edits the source). Indexed in
   `docs/decisions/README.md` (count 205).
5. Rewrite rows D1243, D1252, D1254 and D1247 in §1 with the numbers.

**Targeted:** `test_documentation_index`, `test_acceptance_registry` and
`test_repository_contract` — the three modules that read the ADR index,
derived from the tree (D1263: no generator writes it, so no gate is owed at
this run's close). Then push and read CI.

**Done.** 2026-09-12, on `session-24` at `e3ba687`'s child. Three rigs, each
with its control, in WSL with Docker 29.5.2; the scripts and their outputs are
`/tmp/r24{a,b,c}.py` + `.txt` and copied to the scratchpad under `run1-rigs/`.
Nothing under `src/`, `bin/` or `tests/` moved.

**Rig 24a — the loopback server (9 arms, 9 as designed, 0 mismatches).**
`ss -ltn`: the server bound to `("127.0.0.1", 0)` listens at `127.0.0.1:34273`;
the CONTROL bound to `("0.0.0.0", 0)` at `0.0.0.0:39573`. The second reading,
for the fallback a test needs when `ss` is absent: `socket.connect` from this
host's interface address (`172.25.28.139`) is **refused** by the loopback
server and **connected** by the control, and `127.0.0.1` reaches the loopback
one. `socket.gethostbyname_ex(socket.gethostname())` returns only
`['127.0.1.1']` on this machine, so the address must be read from the
interface (`hostname -I`) — the test in Run 3 takes that path, not the
`gethostbyname_ex` one. `http.server` exposes `Host`, `Origin` and `Cookie` to
the handler as sent. Statuses: no cookie **401**; `/open/<key>` **303** with
`Set-Cookie: apg_studio=…; HttpOnly; SameSite=Strict; Path=/` and `Location: /`;
with the cookie **200**; `Host: evil.example:PORT` **421**; `Origin:
http://attacker.example` **403** and `Origin: http://127.0.0.1:PORT` **200**;
`OPTIONS /__apg/x` **405**; `POST /__apg/x` without `X-Apg-Studio` **403**,
with it **200**. A refused `POST` announcing `Content-Length: 1000000` with one
byte sent: **403**, `Connection: close`, body returned, client did not hang —
so a refusal before `self.rfile` is read is a shape and not a hope.

**Rig 24b — a deployment on loopback (the one that changed the design).**
`apg dev up` 16.4 s; the real auth application on `uvicorn` 0.50.2 in a thread,
ready in 0.4 s, its bound port read from
`server.servers[0].sockets[0].getsockname()` — **the attribute exists**, no
fallback needed; PostgREST with `PGRST_JWT_SECRET=@/etc/postgrest/jwks.json`
over the application's own published JWKS, schema cache in 1.8 s, and the
CONTROL (the HS-secret form `served` uses) loading too, so both forms work at
the pinned image; Traefik published `-p 127.0.0.1:0:8080`, `docker port` →
`127.0.0.1:32923`. Whole rig to its last reading: 35.9 s. Teardown left no
container of this rig's (three pre-existing `apg-auth-endpoints-…`,
`apg-auth-reach-…` and `apg-storage-reach-…` from earlier sessions' aborted
runs are still on this workstation and are not this rig's — noted, not
removed).

- **The surface equality, through an application-issued human token**: `GET
  <edge>/api/rest/` with `Accept: application/openapi+json` → 200, 16035 bytes
  → normalized against the address the deployed document publishes →
  `808ac715c09aeebc382dd5afc886c1680fe2ea9870e729b9d34a623dee8d18de`, **equal
  to `projects/example/contracts/postgrest-openapi.canonical.json` byte for
  byte**, not merely by digest. This is rig 23a's equality for the one token it
  could not use. It took **three arms** to get there and two of them are now
  divergence rows: the raw document fingerprints `f12cdc72c67f98e0…` (D1260 —
  `fingerprint()` does not normalize), and a loopback `http` proxy URI serves a
  document `normalize` **refuses** (D1261 — `schemes ['http']`). Arm C, the
  shape Run 4's fixture must use, is `https://127.0.0.1:<edge port>/api/rest`
  as the proxy URI with the route reached over `http`: `host 127.0.0.1:32923`,
  `schemes ['https']`, fingerprint `808ac715…`, **equal**. ADR 0050's control
  measured: a wrong `expected_host` is refused, never normalized into
  agreement.
- **RLS is PostgreSQL's**: A → 2 notes, B → 1, A asking `owner_id=eq.<B>` → 0.
- **The session plane** (D1252): one login → exactly one row, live; keys
  `session_id, created_at, last_used_at, revoked_at, revoked_reason`;
  `created_at` at **microsecond** resolution — three logins in 0.68 s gave
  three distinct values, so D1252's tie is unreachable in practice and its
  branch is proved as a unit.
- **PostgREST's CORS answer** (D1262): **there is none.** `Origin:
  http://127.0.0.1:1` → 200 with `Connection, Content-Length,
  Content-Location, Content-Range, Content-Type, Date, Server` and no
  `Access-Control-*` header at all — the opposite of what §1 D1243 expected.
- One thing Run 4's fixture needs and no row required: the example project's
  RPC is **`api.create_note(p_title, p_content)`**, not `p_body`. The rig was
  told so by PostgREST's own `PGRST202` hint.

**Rig 24c — the audit reader and 0032.** 33 migrations applied (31 released +
the example set's two), a historical `refused` row seeded before 0027 as the
fixture does (D940). Before: `pronargs` **3**, twelve columns, **no**
`denial_reason`; asking the function for the column → `column "denial_reason"
does not exist`. `CREATE OR REPLACE` with the widened `RETURNS TABLE` →
**`cannot change return type of existing function`** at PostgreSQL 18.4, so the
DROP is required and §9's alternative did not arise. Between the CREATE and the
re-issued GRANT the auth service is answered **`permission denied for function
auth_list_agent_audit`**, and after it reads both rows as the auth service:
`create_note|refused|scope_not_held`, `list_resources|served|NULL`. After:
`pronargs` **3**. The draft body is `run1-rigs/0032-body.sql`; 0032 is written
from it in Run 2 with the `{{auth_service}}` placeholder.

**ADR 0205** written and indexed (count 205). **Five rows added to §1**
(D1259–D1263) and four rewritten with the numbers (D1243, D1247, D1252,
D1254); next free is now **D1264**. The one row that changes a later run's
code is D1260: `surface_answer` gains `expected_host` and `expected_base_path`,
and Run 2 writes that signature rather than the planned one.

### Run 2 — migration 0032, the audit boundary served, and Studio's pure core

**Read first:** `migrations/templates/0020-agent-audit-reader.sql` and
`0027` whole; `docs/migrations.md` (how a migration is numbered, templated
with `{{role}}` placeholders, frozen); `bin/migrate.sh freeze-lock`;
`tests/contract/test_migration_contract.py` (what every migration must
satisfy); `tests/contract/test_agent_audit_plane.py` whole (the cluster proof
this run extends — one of the five rigs D1158 names; note its fixture applies
migrations itself); `tests/contract/test_database_function_signatures.py`
whole (unswept — run it by name); `services/auth-api/app/routes.py` lines
300–360 and 940–1050; `services/auth-api/app/openapi_docs.py` (`DOC_LIST_AUDIT`
/ `RESP_LIST_AUDIT` — where the response schema is declared);
`bin/app-contract.sh` and `test_app_contract_command`; `src/agentic_postgres/
client_ir.py` lines 173–280 and 417–480 (the dataclasses and `build`) and
`bin/api.py` lines 60–135 (the operation table and `perform` — the shape the
forwarder copies); `src/agentic_postgres/dev_environment.py` (a pure module
with a `bin/` driver: the layout `studio.py` copies).

1. **`migrations/templates/0032-agent-audit-reader-boundary.sql`** — the
   next released number after 0031 (`ls migrations/templates | tail -1`).
   Header comment in the tree's voice: what 0027 added, what 0020 never
   returned, why DROP rather than REPLACE (a `RETURNS TABLE` cannot change
   under `CREATE OR REPLACE` — measured in rig 24c: paste the error), why
   the grant is re-issued. The body from rig 24c with the `{{auth_service}}`
   placeholder. `bin/migrate.sh freeze-lock`. `test_migration_contract`
   green; a new proof in it, `test_0032_reissues_the_reader_grant`: the file
   text carries `GRANT EXECUTE ON FUNCTION app_private.auth_list_agent_audit
   (uuid, uuid, integer) TO {{auth_service}}` after its `CREATE` — a scan,
   named as one (D464).
2. **The service.** `routes.py`: `"denial_reason": row["denial_reason"]` in
   the audit row dict, with the comment that it is non-null exactly on
   refused rows by 0027's CHECK; `openapi_docs.py`: the response schema
   gains `denial_reason` (nullable string, the enum's members listed by
   reading 0027 — or `type: [string, null]` with the description naming the
   enum; copy the form the file already uses for nullable members).
   `repository.py` needs nothing (`SELECT *`). `bin/app-contract.sh --update`
   → the canonical document moves by exactly that member (assert the diff by
   eye and in the Done paragraph); `bin/app-contract.sh --check` exit 0.
3. **The client regenerated** (D1238): `bin/apg.sh generate --project
   project.example.yaml`; read `clientVersion` in `contract.ts` and what
   `classify_changes` returned (the app digest moved; the three wrapped auth
   operations did not — record the class the rule chose; if it chose
   nothing and the version did not move while a digest did, that is a
   divergence row, not a thing to fix silently); `generate --check` exit 0.
4. **The cluster proof** in `tests/contract/test_agent_audit_plane.py`:
   `test_the_audit_read_returns_the_boundary_exactly_on_refused_rows` — the
   rig-24c sequence as a test: one served row, one refused row with the first
   enum member, the function called as the auth service role, the refused
   row's `denial_reason` equal and the served row's `NULL`; the CONTROL
   inside the same test: `pronargs` is 3. And in `test_auth_endpoints.py`
   (the ASGI rig): `test_admin_audit_serialises_the_denial_boundary` — an
   administrator with `admin_audit:read` (extend `ADMIN_SCOPES` in that
   module — grep every reader of that constant first) reads `/admin/audit`
   after the two rows and the JSON carries the key on both rows with the two
   values. Run `test_database_function_signatures` by name.
5. **`src/agentic_postgres/studio.py`** — pure, no I/O, stdlib +
   `agentic_postgres` only (HOST_PACKAGES), with these names and no others
   at module level (a test asserts the public set so a later addition is a
   decision):
   - constants: `BIND_ADDRESS = "127.0.0.1"`, `STUDIO_MAX_ROWS = 1000`,
     `AUDIT_PAGE_LIMIT = 500`, `STUDIO_REFRESH_BEFORE_SECONDS = 120`,
     `LAUNCH_COOKIE = "apg_studio"`, `CUSTOM_HEADER = "X-Apg-Studio"`,
     `CONTENT_SECURITY_POLICY` and `SECURITY_HEADERS` (§8's exact values),
     `SURFACE_ANSWERS = ("ok", "stale_contract", "unreachable", "unreadable")`;
   - `class StudioError(ValueError)` carrying `exit_code`;
   - `address_book(document) -> AddressBook` (frozen dataclass `rest_url`,
     `app_url`): refuses `document_kind != "deployed"` (exit 2, `bin/api.py`'s
     message), a route not `ready` (exit 5), a non-`https` URL whose host is
     not `127.0.0.1`/`localhost` (exit 5, naming the URL's scheme and host —
     never the URL's query or userinfo);
   - `surface_answer(ir, fetched: bytes | None, error: str | None) ->
     SurfaceAnswer` (frozen: `answer`, `served_sha256 | None`,
     `expected_sha256`, `reason | None`): `unreachable` when `error` names a
     transport failure, `unreadable` when the bytes are not JSON or
     `normalize` refuses, `stale_contract` naming both, else `ok`;
   - `rest_query(ir, *, relation, select, filters, order, limit) -> str`
     (D1250) returning `"/<relation>?select=…&<col>=<op>.<quoted value>&
     order=<col>.<asc|desc>&limit=<n>"`, every refusal a `StudioError(422)`
     naming what was refused and the set it was checked against;
   - `FORWARDER_TABLE: dict[str, Operation]` — frozen `Operation(method,
     path_template, scope_hint, body_allowed)` for exactly: `surface` (`GET
     <rest>/`), `query` (`GET <rest>/<rest_query>`), `me` (`GET /auth/me`),
     `sessions` (`GET /auth/sessions`), `agents` (`GET /admin/agents`),
     `audit` (`GET /admin/audit`), `revoke_agent` (`PATCH
     /admin/agents/{agent_id}`); `test_the_forwarder_table_has_no_rest_write`
     asserts every `<rest>` entry is `GET`;
   - `revoke_request(agent_id, confirm) -> tuple[str, dict]` refusing
     `confirm != agent_id` with the shell's sentence (D1251), and refusing an
     `agent_id` that is not a UUID before that;
   - `request_checks(*, host, bound, cookie, expected_cookie, origin,
     own_origin, method, custom_header) -> int | None`: the status to refuse
     with (421, 401, 403, 405) or `None` — one pure function the server calls
     first on every request, so the battery can reach every branch;
   - `own_session(rows, since) -> str | None` (D1252): the live row with the
     newest `created_at` strictly after `since`; `None` on a tie or on none;
   - `audit_view_header(shown, total) -> str` returning `showing {shown} of
     {total} rows on this page; the page is the newest {AUDIT_PAGE_LIMIT}`;
   - `redact_for_log(method, path) -> str` (D1256): the path split at `?`
     and the `/open/<key>` segment replaced by `/open/<key>`.
6. **`tests/contract/test_studio_core.py`** (marked `contract`, `p0`,
   `security` — D1240: the marks FIRST) over every function above:
   `test_the_schema_view_is_the_ir_and_nothing_else` (`schema_view(ir)`, add
   it: relations/columns/types/enums/RPCs from the IR — assert the JSON's
   key set equals the IR's, and that a relation not in the IR is absent),
   the four `rest_query` proofs, the forwarder-table proof, the
   `revoke_request` proof, `request_checks` over a table of 12 inputs (each
   refusal and each pass), `own_session` (determined / tie / none),
   `audit_view_header`, `redact_for_log`, and `test_the_public_surface_is_the_declared_set`.
7. Battery (≥8 mutations: drop the tie branch in `own_session`; accept an
   operator not in the set; make `request_checks` return `None` for a foreign
   `Origin`; change a `<rest>` entry to `POST`; make `revoke_request` compare
   `confirm` to itself; encode a value with `safe=","`; loosen the `https`
   rule to any host; drop `denial_reason` from the route dict), each with a
   paired control.

**Targeted:** `test_studio_core`, `test_migration_contract`,
`test_agent_audit_plane`, `test_auth_endpoints`,
`test_database_function_signatures` (by name), `test_app_contract_command`,
`test_client_typescript`, `test_generate_command`, `test_acceptance_registry`
(a renamed or added test in an existing module, D1119), plus every module
`git grep -ln "auth_list_agent_audit\|ADMIN_SCOPES\|list_agent_audit" -- tests
src services bin` names. Push; read CI.

**Done.** 2026-09-12 at `4af67ca`'s child. Migration `0032` released, the
boundary served, and Studio's pure core with 25 proofs over it. Targeted list
run once at the close: **427 passed in 135 s**, no failures and no skips, over
`test_studio_core`, `test_migrations`, `test_agent_audit_plane`,
`test_auth_endpoints`, `test_database_function_signatures` (by name — D1240's
unswept module, and 0032 moves a function signature), `test_denial_taxonomy`,
`test_mcp_tools`, `test_fleet`, `test_app_contract_aggregate`,
`test_client_typescript`, `test_generate_command`, `test_client_ir` and
`test_acceptance_registry`. The list is the grep's, not the plan's: every
offline module `git grep -ln "auth_list_agent_audit\|list_agent_audit\|
denial_reason" -- tests src services bin` names (D1146, D1149).

**Migration 0032.** `20260912120032`, placeholders `object_owner` and
`auth_service`, `freeze-lock` clean at 32 migrations. DROP + CREATE, because
`CREATE OR REPLACE` is refused by PostgreSQL 18.4 with *cannot change return
type of existing function* — rig 24c's measurement, pasted into the file's
header. `pronargs` 3 before and after, so ADR 0175's guard and
`repository.py`'s three-parameter call are untouched. The grant is re-issued
because a DROP takes it: measured, *permission denied for function
auth_list_agent_audit* between the CREATE and the GRANT.

**The service.** `routes.py` serialises `denial_reason` on every row, with the
comment that it is non-null exactly on refusals by 0027's CHECK and null on a
refusal recorded before that column existed (D940's NOT VALID). The app
contract moved by **exactly one line** — the endpoint's description — and not
by a member, because the 200 carries no schema (D1265). `app-contract.sh
--check` exit 0.

**The client** (D1238): regenerated in the same commit; `app_openapi_sha256`
`f21bf4a8…` → `e477fd23…`, `clientVersion` unchanged at 1.0.0 and
`classify_changes` returning nothing. That is §9's stop condition and it was
read rather than accepted: D1266 records why the version rule is right and
what it costs.

**Studio's core.** `src/agentic_postgres/studio.py`, 12 public functions and 11
constants, stdlib + `agentic_postgres` only, `__all__` compared against the
module's own AST so a name added later is a decision. Two signatures differ
from the plan's and each has a row: `surface_answer` takes the expected address
(D1260) and `request_checks` takes the path (D1267). The operator wire table is
a second copy of `app.mcp_query.OPERATORS` with the comparison test beside it
(D486), because an operator command may not import the service.

**The battery: 14 mutations, 14 killed**, each with a paired control the
mutation cannot reach, run in the same invocation, every anchor pre-flighted to
match exactly once, restored by copy and `cmp`ed back. Eleven over `studio.py`
against `test_studio_core`, one over `routes.py` against `test_auth_endpoints`,
two over the migration.

**Two of them first came back ERROR on the target AND the control, and that
reading is the run's find** (D386). Neither was a survivor; both were
mutations that never reached an assertion:

* dropping the GRANT gives `MigrationError: 20260912120032: declares
  placeholders its template never uses: ['auth_service']` — **the product
  refuses it one level above the scan**, when the manifest loads. So the scan
  is a second guard rather than the only one, which is worth knowing: the
  representative mutation drops the placeholder too, and then the scan is what
  fails (killed).
* dropping `denial_reason` from the `RETURNS TABLE` leaves the previous line's
  trailing comma and the migration never applies (`syntax error at or near
  ")"`). The representative mutation drops it from the `SELECT` list as well,
  and the cluster proof is what fails (killed).

A migration is digested by `released.lock.json`, so both re-freeze the lock
while mutated and restore it with everything else.

**Numbers read by the new proofs.** The cluster proof: `create_note|refused|
scope_not_held` and `list_resources|served|NULL` through the function as the
auth service, `pronargs` 3. The endpoint proof: the refused row's
`denial_reason` is `scope_not_held` and the served row's key is present and
null. Both had never run before this run; both passed on first execution, which
is the first time in this project that thirteen-for-thirteen streak has not
grown.

### Run 3 — the process: `apg studio`, login, the surface check, the forwarder

**Read first:** `bin/dev.py` and `bin/dev.sh` whole (the driver/wrapper
shape, the exit-code block, `--project` resolution, the *unrendered* refusal
with the render command); `bin/generate.py` lines 190–260 (how the IR is
built from `--project` and the render); `bin/api.py` `perform` (urllib
request shape; `Authorization` header; the `HTTPError` split);
`services/docs/serve.py` whole (the fixed table, the handler, the headers, the
signal handling); `bin/dev-token.sh` header (the credential rule);
`tests/contract/test_dev_command.py` and `test_generate_command.py` (the
command-proof shapes); rig 24a and 24b scripts and their outputs.

1. **`bin/studio.py`** (imports: stdlib + `agentic_postgres` — `studio`,
   `client_ir`, `openapi_normalize`, `rendering`/whatever `generate.py` uses
   to load the four inputs; **copy `generate.py`'s loading sequence, do not
   re-derive it**):
   - arguments: `--project FILE` (required), `--outputs FILE` (required, the
     deployed document — the identifier is `document` in this file, D1184),
     `--username NAME` (optional; prompted on a TTY when absent),
     `--password-file FILE` (optional; must be a regular file at mode 0600 or
     stricter and owned by the caller — refused otherwise with exit 2; when
     absent, `getpass.getpass` on a TTY; when absent and no TTY, exit 2
     naming the flag). **No `--password`; no environment variable is read
     for it; a test greps the source for `environ` and `getenv` and asserts
     the only reads are the ones the appendix lists (none).** `--help`.
   - sequence, each step with its exit code: (1) parse (2 before any read);
     (2) `document` loaded and `address_book` (2/5); (3) the IR built as
     `generate` builds it (4 with the render command when unrendered); (4)
     login: `POST <app>/auth/login` → on 401 exit **6** *"the deployment
     refused this credential"* and nothing else (ADR 0097: the endpoint fails
     identically four ways and so does this line); on transport failure exit
     9; record `expires_at`, the refresh token, and `since = time before the
     request`; (5) `GET /auth/sessions` → `own_session` (D1252); (6) the
     surface: `GET <rest>/` with the bearer and `Accept:
     application/openapi+json` → `surface_answer` — printed as one line
     (`studio: surface ok 808ac715…` / `studio: surface stale_contract served
     … expected …; run bin/apg.sh generate --project <path>` / `unreachable:
     <reason>` / `unreadable: <reason>`), never an exit; (7) bind
     `ThreadingHTTPServer((studio.BIND_ADDRESS, 0), Handler)`, generate the
     launch key (`secrets.token_urlsafe(32)`), print exactly one line
     `studio: open http://127.0.0.1:<port>/open/<key>` and one line naming
     the subject and the deployment's key (`studio: as <username> on
     <project key>`); (8) serve until SIGINT/SIGTERM; (9) on exit `DELETE
     /auth/sessions/<own>` or the ADR 0195 line, then exit 0.
   - the handler: `request_checks` first on every request (the refusals
     send status + `Connection: close` and read no body); `/open/<key>`
     sets the cookie and 303s to `/`; `/`, `/studio.js`, `/studio.css` from
     `services/studio/` by a fixed table (bytes read once at start); every
     response carries `SECURITY_HEADERS`; `/__apg/state` (the surface answer,
     the subject, the project key, the IR's digests, `own_session is None`);
     `/__apg/schema` (`schema_view(ir)`, refused 409 unless the surface is
     `ok`); `/__apg/query` (POST JSON → `rest_query` → one upstream GET →
     the rows relayed as JSON with the upstream STATUS CLASSIFIED — `ok`,
     `refused` (401/403), `invalid` (4xx with PostgREST's `code` relayed as a
     code and nothing else, ADR 0139's rule), `upstream_failed` (5xx/
     transport) — and never the upstream body verbatim, D433); `/__apg/audit`
     (GET with optional `agent_id`/`owner_id` → upstream with `limit=500` →
     rows + `audit_view_header`); `/__apg/agents`, `/__apg/me`,
     `/__apg/sessions`; `/__apg/revoke` (POST `{agent_id, confirm}` →
     `revoke_request` → PATCH). The bearer is refreshed by a lock-guarded
     helper when `expires_at - now < STUDIO_REFRESH_BEFORE_SECONDS`.
     `log_message` overridden with `redact_for_log`.
   - Every upstream call has a 10 s timeout and `Accept: application/json`;
     `Content-Type` only on the PATCH.
2. **`bin/studio.sh`** — the `dev.sh` wrapper shape: `set -euo pipefail`, a
   usage block naming the four surface answers and the exit codes (0 / 2 /
   3 / 4 / 5 / 6 / 9), `exec "$(python_bin)" "${ROOT_DIR}/bin/studio.py"
   "$@"` (copy the interpreter resolution `dev.sh` uses). `chmod 755` both.
   `SHELL_COMMANDS` and `PYTHON_COMMANDS` gain them; `test_cli_contract` in
   the targeted list (D1014); **`git add` the two files before running it**
   (D1188).
3. **`services/studio/index.html`, `studio.js`, `studio.css`** — minimal in
   this run: the page loads `/__apg/state` and shows the surface line, the
   subject and the project; a *Schema* section listing relations from
   `/__apg/schema` (hidden with the state's reason when not `ok`); nothing
   else yet. `studio.js` is one file, no framework, `fetch` with
   `credentials: "same-origin"` and the custom header on every call. A
   `README.md` beside them saying these three files are served by
   `bin/studio.py` and are not a container.
4. **`tests/contract/test_studio_command.py`** (`contract`, `p0`,
   `security`): the dispatcher proof; `--help`; exit 2 before any read (a
   `--project` that does not exist with a malformed flag → 2, and the
   missing file is NOT what the message names); exit 4 with the render
   command; exit 5 for a document with `routes.rest.status != ready`, and
   for `http://example.invalid/…`, and that `http://127.0.0.1:1/…` is NOT
   refused at that step (it fails later, at login, as `unreachable` → exit
   9); the password rules (a `--password` flag → 2 as unknown; a 0644
   password file → 2 naming the mode; `APG_STUDIO_PASSWORD` in the
   environment ignored — the proof sets it and asserts the process still
   prompts/refuses); `test_a_refused_login_exits_six_and_says_no_more`
   against a tiny stdlib stand-in that answers 401 to `/auth/login` (the
   stand-in is for the REFUSAL LINE only — every positive path is proved in
   the runtime module against the real app); nothing printed is a credential.
5. **`tests/contract/test_studio_server.py`** (`contract`, `p0`,
   `security`): Studio started as a subprocess against the SAME stand-in
   (which answers 200 to `/auth/login` with a fake token, `[]` to
   `/auth/sessions`, and 200 with the fixture snapshot's bytes to `<rest>/`
   so the surface answers `ok`), reading the printed URL; then the seven
   `STU-BIND-001` proofs, `test_every_response_carries_the_csp_and_security_headers`,
   `test_studio_holds_no_key_and_verifies_nothing` (AST over `bin/studio.py`
   and `studio.py`: no import of `jwt`, `jwks`, `cryptography`, `jose`,
   `hashlib` used on a token — and the stand-in's refused-token arm: a 401
   from `/auth/me` reaches the page as `{"status": "refused"}` with no body
   text), `test_an_upstream_refusal_is_classified_and_its_body_is_not_relayed`
   (the stand-in answers 403 with a distinctive body; the page's JSON does
   not contain it), `test_the_listener_is_on_loopback_and_nowhere_else`
   (`ss -ltn` when present, else a `socket.connect` to `0.0.0.0:port` from
   the same host expecting refusal — record which ran, D1239's shape).
   **The stand-in is a test double of an HTTP shape, not of the product, and
   the module's docstring says so**: it exists so the server's own rules can
   be proved in two seconds; the runtime module is the proof against the
   product.
6. Battery over Runs 2–3's tests (≥10): remove `request_checks` from the
   handler; bind `0.0.0.0`; print the token on the `open` line; read the
   password from `APG_STUDIO_PASSWORD`; relay the upstream body; drop a
   security header; serve `/__apg/schema` under `stale_contract`; accept a
   0644 password file; exit 0 on a refused login; log the query string.

**Targeted:** `test_studio_command`, `test_studio_server`, `test_studio_core`,
`test_cli_contract`, `test_operator_commands_run_on_the_host`,
`test_repository_contract`, `test_printed_commands`, `test_root_script_policy`
(a new `bin/*.py`), `test_acceptance_registry`. Push; read CI.

**Done.** 2026-09-12 at `34a3b28`'s child. `apg studio` exists: a verb of the
dispatcher (derived from `bin/*.sh`, so nothing was registered by hand), a
wrapper, a process, three first-party files and 30 proofs over them. Targeted
list run once at the close: **895 passed, 2 skipped** in 40 s over
`test_studio_command`, `test_studio_server`, `test_studio_core`,
`test_cli_contract`, `test_operator_commands_run_on_the_host`,
`test_repository_contract`, `test_printed_commands`, `test_root_script_policy`
and `test_acceptance_registry`. The two skips are `test_root_script_policy`'s
own, for two shell commands that run no Python.

**What the stand-in answers.** `test_studio_server.py`'s `StandIn` is one
loopback `ThreadingHTTPServer` answering `/auth/login` (200 with a distinctive
token, or whatever an arm sets), `/auth/sessions`, `/auth/me`, `/admin/agents`,
`/admin/audit` and `<rest>/` with the committed snapshot re-addressed to
itself. It is a double of an HTTP SHAPE and its docstring says so; every
positive path against the product is Run 4's. The re-addressing is D1261's:
`host` is the server's own and `schemes` stays `["https"]`, because the
normalizer refuses `["http"]` and the field describes the address a caller was
told to use.

**`ss` was available** on this machine, so the loopback proof took both
readings: `ss -ltn` shows the socket on `127.0.0.1` only, and a `socket.connect`
from the interface address (read from `hostname -I`, never from
`gethostbyname_ex` — rig 24a measured that returning `['127.0.1.1']` here) is
refused. The test asserts it ASKED: a run where neither reading was available
fails rather than passes.

**Three defects, found by the proofs before the battery existed**, each now a
row: `OPTIONS` reached `http.server`'s own 501 with none of our headers
(D1268); the wrapper reported a missing file where an unknown flag was typed
(D1269); and the header proof compared the product to itself (D1270, found by
the battery). **Two released guards also caught the new command and both were
right** (D1271) — neither was weakened.

**The battery: 12 mutations, 12 killed**, after a first pass of 8/12 that is
the more useful number. One survivor was real (M6, the weak header proof) and
three were **broken pairings** — the control was reachable by the mutation, so
both sides failed and the arm said nothing. Re-paired: M5's control read the
same relayed body, M9's control asserts exit 6 from a refused login, and M11's
control drives an `OPTIONS` of its own. A control that the mutation can reach
is not a control (D499), and a battery that counted those as survivors would
have sent this run looking for three defects that were not there.

**Run 2's CI came back red on one proof, and the proof is right** (D1273):
`test_no_module_is_imported_only_by_its_own_tests` refuses a package module
whose only importers are its own tests, and at `34a3b28` `studio.py` was
exactly that -- its caller lands here. Both CI jobs failed on that one
assertion and nothing else (`1 failed, 5507 passed` and `1 failed, 5597
passed`), and **this run's own commit `deb4aa9` is green**. Read rather than
worked around: the split between Run 2 and Run 3 is
a reviewing convenience and D204 is a property of the tree at every commit.

**The three assets**: `index.html` 35 lines, `studio.js` 131, `studio.css` 135,
plus a `README.md` saying why there is no Dockerfile and no `package.json`. No
external reference, no inline script, no `style=`, no build step. Run 4 adds
the query, audit, capability, agent and session views to them.

### Run 4 — the views, the runtime proof, and the negative tests

**Read first:** rig 24b's script (the fixture this run turns into
`tests/contract/test_studio_runtime.py`'s module fixture); `tests/contract/
test_generated_client_runtime.py` lines 411–660 (how a subprocess result is
read, `steps()`, `test_nothing_any_container_prints_is_the_token`);
`tests/deployment/conftest.py` `audit_admin` (the scopes an audit-capable
subject carries — copy the list); `tests/contract/test_agent_audit_plane.py`
(writing audit rows through the definer functions);
`services/auth-api/app/service.py` lines 440–470 and 560–610 (what a revoked
agent can and cannot do); the Session 16 `refused()` helper
(`test_session16_agent_governance.py:103`).

1. **The fixture `studio_rig`** (module scope, in `test_studio_runtime.py`):
   rig 24b as a fixture — `apg dev up`, PostgREST, Traefik published on
   `127.0.0.1:0`, the auth app on uvicorn in a thread, one administrator
   (all admin scopes INCLUDING `admin_audit:read`, `admin_agents:read/write`,
   `admin_users:write`), users A and B with two and one notes, a
   `document_kind: deployed` document written to `tmp_path` with the two
   loopback URLs (copy the fixture project's rendered `outputs.json` and
   rewrite `routes.rest.url`, `routes.app.url`, both `status: ready`,
   `document_kind`), the administrator's password in a 0600 file, and a
   helper `launch(username, password_file) -> StudioProcess` (subprocess,
   the URL read from stdout with a 30 s deadline, `kill` + stderr captured
   in `finally`) and `browser(process) -> Callable` (an `http.client`
   session holding the launch cookie and sending the custom header — the
   page's role, played by the test). Everything removed in `finally`.
   **Record the fixture's wall time in the Done paragraph** (D1211's cost,
   restated for this rig).
2. **The views** in `studio.js`/`index.html`/`studio.css`: *Schema*
   (relations → columns/types, enums, RPCs with arguments); *Query* (a
   relation select, column checkboxes, filter rows `[column][operator][value]`
   with `+`, order, limit default 100 — submit → `/__apg/query` → a table);
   *Audit* (fetch on open; a table with EVERY column the endpoint returns,
   `denial_reason` rendered in its own column and a refused row visibly
   marked; view filters over agent/tool/outcome/boundary/time-range as
   text inputs that hide rows in the DOM only; the header from
   `audit_view_header` always visible); *Capabilities* (the IR's tools:
   name, kind, arguments, scopes; the lock's `tools_sha256` and a fixed
   sentence: *this is the checkout's compiled lock; whether the plane serves
   it is `bin/apg.sh doctor`'s question*); *Agents* (`/__apg/agents` → a
   table; a *Revoke* control per row that reveals an input *type the agent
   id to confirm* and posts `{agent_id, confirm}`; the 422 sentence shown
   verbatim); *Session* (`/__apg/me`, `/__apg/sessions`, the own-session
   line). No inline `<script>`, no inline `style=`, no external reference.
3. **`tests/contract/test_studio_runtime.py`** (`contract`, `p0`,
   `database`, `security`), every proof through `launch` + `browser` — the
   product's own command and the page's own calls, never a Python
   re-implementation of the forwarder (D1114):
   - `test_launch_answers_ok_against_the_surface_the_ir_was_built_from`
     (state's `answer == "ok"`, `served_sha256 == expected`);
   - `test_launch_answers_stale_contract_naming_both_digests_and_refuses_the_rest_views`:
     a SECOND Studio against a document whose `rest_url` points at a stand-in
     serving a different document (the Run 3 double, with one byte of a
     description changed) → `stale_contract`, both digests in the state,
     `/__apg/schema` 409, `/__apg/audit` 200 (the application views remain);
   - `test_unreachable_and_unreadable_are_two_answers` (`rest_url` at
     `http://127.0.0.1:9/` → `unreachable`; a stand-in answering `not json`
     → `unreadable`);
   - `test_a_query_as_a_returns_as_rows_and_none_of_bs` (Studio launched as
     A; `/__apg/query` over `notes` → 2 rows, none with B's owner; a second
     Studio as B → 1);
   - `test_a_query_syntax_value_finds_nothing_and_the_stored_value_is_found`
     (D1250's pair);
   - `test_the_audit_view_renders_every_row_of_the_page_with_its_boundary`
     (rows written through the definer functions: 3 served, 2 refused with
     two different boundaries; `/__apg/audit` as the administrator → 5 rows,
     the two `denial_reason`s present, the header `showing 5 of 5 rows on
     this page; the page is the newest 500`);
   - `test_the_audit_page_count_equals_the_tables_newest_rows` (write 520
     rows in a loop through the functions; `/__apg/audit` → 500; `psql` as
     the superuser over the rig: the newest-500 count → 500 and the total
     520 — the number the header cannot show and the proof says so);
   - `test_a_view_filter_hides_no_row_from_the_pages_count` (the page's
     JSON carries `total` and `rows`; a filter is the page's concern — assert
     the endpoint returns all rows regardless of any filter parameter the
     page might send, i.e. `/__apg/audit?outcome=refused` is 400 (the
     forwarder takes only `agent_id`/`owner_id`), which is the proof that
     filtering cannot happen upstream of the count);
   - `test_a_token_without_the_audit_scope_is_refused_and_classified`
     (Studio as A → `/__apg/audit` → `{"status": "refused"}`);
   - `test_revocation_through_studio_stops_the_agents_next_exchange` (an
     agent created through `POST /admin/agents` as the administrator (the
     conftest `create_reader` shape, in-rig); its secret exchanged once at
     `/auth/agent-token` → 200; `/__apg/revoke` with `confirm` wrong → 422
     and the exchange still 200 (the control); with `confirm == agent_id` →
     200; the exchange → 401; `SELECT app_private.agent_claims_are_current(
     <id>, <role>, <scopes>, <version>)` → NULL);
   - `test_studio_ends_the_session_it_began` (`/auth/sessions` as the same
     subject through a direct login BEFORE and AFTER `SIGTERM` to Studio: the
     row Studio created has `revoked_at` set after);
   - `test_studio_refreshes_before_expiry` — **measure first whether the
     rig's app honours a shorter TTL through settings** (`MAX_TTL_SECONDS`
     is a constant, so probably not): if it does not, the proof drives the
     refresh helper directly with a monkeypatched clock in `test_studio_core`
     and THIS test asserts only that `/auth/refresh` is in the forwarder's
     upstream calls (the double records them) — and the row says so;
   - `test_no_page_response_header_or_asset_carries_the_token` and
     `test_nothing_studio_prints_is_a_token_a_key_or_a_value` (D1256).
4. **`tests/contract/test_studio_assets.py`** (`contract`, `p0`, `security`):
   `test_studio_assets_carry_no_third_party_code` (the three files and
   nothing else under `services/studio/` but `README.md`; no `package*.json`;
   no `://` outside comments — strip comments first, D1197);
   `test_the_page_carries_no_inline_script_and_no_external_reference`
   (parse `index.html`: every `<script>` has `src="studio.js"` and no body;
   every `<link>` is `studio.css`; no `style=` attributes; no `on*=`
   attributes).
5. Battery (≥12): the RLS proof's control (serve B's rows to A — reachable
   only by a rig change, so instead: the forwarder drops the bearer → the
   proof must fail as `refused`, not pass with zero rows — assert HOW);
   render only `served` rows; drop `denial_reason` from the row; cap the
   page at 100 and keep the header at 500; accept `outcome` upstream; skip
   the confirm check; skip the session end; relay the 403 body; add an
   inline `<script>`; add `https://example` in a comment (the scan must
   still pass — the control that it strips comments) and outside one (must
   fail); serve the schema under `stale`; log the query.

**Targeted:** `test_studio_runtime`, `test_studio_assets`, `test_studio_core`,
`test_studio_server`, `test_studio_command`, `test_acceptance_registry`. Push;
read CI. **CI's Session 2 job now runs the rig** — read its wall time in the
run log and record it.

**Done.** Six views in `services/studio/`, `tests/contract/test_studio_runtime.py`
(17 proofs) and `tests/contract/test_studio_assets.py` (2), and one product
change the rig forced.

**The fixture costs 59 s for the whole module** on this workstation — the rig
built, seventeen proofs run, everything torn down — against rig 24b's 40 s to
the same point and D1211's ~3 min estimate for a PostgREST rig. `apg dev up` is
16 s of it. Module scope is what makes that one price rather than seventeen.

**Rig 24d, and the run's find** (D1275). The first execution of the `ok` proof
answered `stale_contract` for the administrator, so the question got a rig: one
URL, three tokens the auth application issued. `authenticated` → 16,024 bytes,
8 paths, 3 definitions, fingerprint `808ac715…`, EQUAL to the committed
snapshot. `project_admin` → 2,393 bytes, **1 path, 0 definitions**, fingerprint
`1da00c11…` — and `anon` → the same 2,393 bytes and the same fingerprint. The
administrative role holds nothing in `api`, so PostgREST serves it the
anonymous document. The ANSWER was right; the launch line was not, and now
names both causes rather than sending an administrator to regenerate a correct
capture.

**The refresh measurement** (the plan asked for it first): the rig's
application cannot issue a short-lived token. `app.service.TOKEN_TTL_SECONDS`
is `claims.MAX_TTL_SECONDS`, a module constant of 900 with no settings path,
and rig 24b read `expires_at` back from a real login 900 s out. So
`test_studio_refreshes_before_expiry` drives the product's own
`Upstream.bearer` against a stand-in whose login hands out a token expiring in
10 s, and asserts `POST /auth/refresh` is among the calls the double recorded —
which is better than the monkeypatched clock the plan offered as the fallback,
because it exercises the real helper. The control is the other sixteen proofs:
they run against the real application at 900 s and none of them refreshes.

**Every number the proofs read**: 2 notes as A and 1 as B, with none of B's
owner in A's rows; 5 audit rows for one owner, 3 served and 2 refused at two
different boundaries; 520 rows written for one agent, 500 served, the header
*“showing 500 of 500 rows on this page; the page is the newest 500”*, and 520
counted over the table as the superuser — the number the page cannot show; 400
for each of `outcome`, `denial_reason` and `since`, with `agent_id` accepted as
the control; `/auth/agent-token` 200 → 422 → **still 200** → 200 → 401, and
`agent_claims_are_current` NULL after.

**The battery: 14 arms, 14 as expected, first pass.** Thirteen mutations killed
and one negative control held.

| arm | mutation | killed by | control |
|---|---|---|---|
| M1 | the forwarder drops the bearer | the RLS proof, **on `refused`** not on a count | the asset scan |
| M2 | only `served` rows are rendered | the five-row boundary proof | the 520-row page proof (all served) |
| M3 | the endpoint stops serving `denial_reason` (0032 undone) | the boundary proof | the page proof |
| M4 | the page is capped at 100, the header still says 500 | the page proof | the boundary proof (5 rows fit either cap) |
| M5 | `outcome` is passed upstream | the filter proof | the boundary proof (`owner_id` only) |
| M6 | the typed confirmation is not checked | the revocation proof | the boundary proof |
| M7 | the launch does not end its session | the session proof | the `ok` launch |
| M8 | an upstream refusal body is relayed | the audit-scope proof | the boundary proof |
| M9 | the schema view is served under `stale` | the stale proof | the `ok` launch (the gate never fired) |
| M10 | the capabilities view is gated on the surface | the capabilities proof | the `ok` launch |
| M11 | the log keeps the query string | the log proof | the `ok` launch |
| M12 | an inline `<script>` | the page parse | the third-party scan |
| M13 | `https://fonts.example.test` outside a comment | the third-party scan | the page parse |
| C1 | the same URL **inside** a comment | *both must pass* — HELD | — |

M1 is the arm the plan asked for by name: a refusal and an empty result are the
same count, so the battery asserts the failure text says `refused`. C1 is what
makes M13 evidence rather than a scan that deletes what it looks for.

### Run 5 — the envelope, the documents, the threat model

**Read first:** `docs/capacity-envelope.md` lines 180–260 (the `apg
generate` and typecheck MACHINE rows — the exact form to copy);
`bin/render-capacity-envelope.py` (what is rendered and what is hand-written
— **measure which before editing**); `tests/contract/test_capacity_envelope.py`
(how the Session 23 rows are asserted); `docs/generated-clients.md` (the
document Session 23 wrote for its command — the shape `docs/studio.md`
copies); `docs/threat-model.md` whole; `README.md`'s status paragraph and
the *What is intentionally unavailable* section; `docs/api-surface.md` and
`docs/api-operations.md` (whether the audit endpoint's response is
documented there — grep `admin/audit`).

1. **Three MACHINE rows** measured with the product's own command against
   rig 24b (a `/tmp` script that starts the rig, launches Studio three times,
   and times: `apg studio` start → the `open` line; `curl -s -o /dev/null -w
   %{time_total}` on `/` with the cookie; the same on `/__apg/schema`),
   conditions: this machine, the fixture project (7 relations / 7 tools —
   read the IR, do not recall), images cached. Written in the envelope's
   form and asserted by `test_the_envelope_carries_studios_three_latencies`
   (the row present, three samples each, the conditions named) and
   `test_the_envelope_is_current`.
2. **`docs/studio.md`**: what Studio is (ADR 0205 in a page), how to launch
   it (the exact command against an op-owned deployed-document copy), the
   four surface answers and what each means, what each view shows and what
   it cannot (the audit page's boundary; the capability inspector's
   sentence), the revocation confirmation, the session end, **what Studio
   never does** (the stage plan's *must not* list, each with the test that
   proves it), the exit codes, and *If something goes wrong* (the six
   refusals a launch can end in, each with its exit code and the command to
   run next). Indexed in `docs/README.md`; `test_documentation_index` green.
3. **`docs/threat-model.md`**: a *Studio* entry under *Threats* — a web page
   in the human's browser is on the same machine as a token-holding
   process: what a hostile page can do (make the browser send requests to
   `127.0.0.1:<port>`) and what stops it (the cookie is `SameSite=Strict`,
   the custom header is not a simple header, `OPTIONS` is refused, `Host` is
   checked, `Origin` is checked), what a hostile LOCAL process can do (read
   the terminal's scrollback for the launch URL — named as the residual, the
   same one Jupyter accepts, bounded by the process lifetime and by the
   token's 900 s), and PostgREST's default CORS header verbatim from rig 24b
   with the sentence that Studio's design makes it irrelevant because the
   page never holds a token. Under *Notes on residual risk*: the audit
   table's growth (D1255).
4. **README**: the status paragraph at Session 24 (the bump itself is Run
   6's; write the prose now with `1.5.0` and let Run 6's guard confirm);
   *Adopt `1.5.0`* stub after Run 6; a *Studio* paragraph in the human's
   section; every `--through-session 23` a reader is told to type moved to
   24 (`grep -rn "through-session 23\|--session 23" README.md docs/*.md`,
   D693 — **but only in text that tells a reader what to type**; the record
   of what Session 23 did keeps its number).
5. **`docs/scope-closure.md`**: §1's numbers **counted, not recalled**
   (D1194) — requirements 213, claims 122, migrations 32, ADRs 205, D1–D12xx
   as of this run; a new §13 *What Session 24 left open* from §10 below
   (retention STATED with the Run 7 counts to be filled; the audit filter
   widening priced; the rotation still recommended; the two D1248/D1255
   rows).

**Targeted:** `test_capacity_envelope`, `test_documentation_index`,
`test_session12_documented_path`, `test_repository_contract`, plus any module
`git grep -ln "capacity-envelope\|threat-model" -- tests` names. Push; read CI.

**Done.** Three envelope rows, `docs/studio.md`, the threat model's Studio
analysis, the README's Studio section and the ledger's §13 — plus the repair of
Run 4's CI, which is the run's first fact.

**Run 4's CI was red and the fixture was right to be** (D1276). Seventeen
errors, all at `studio_rig`, all `PoolTimeout` behind *connection to server at
`127.0.0.1`, port 32782 failed: Connection refused* — while `docker exec psql`
against the same container in the same fixture had succeeded twice, seconds
earlier. `apg dev up` publishes `127.0.0.1:0:5432` deliberately (D1175), and a
host-to-loopback DNAT is something a daemon can be configured not to make work;
every other cluster this suite starts publishes on all interfaces, which is why
no other rig had met it. The fixture now PROVES an address — the published port,
else the container's own, else a failure naming both and what `docker exec`
could do — and records which answered. 17 passed again locally in 67 s.

**The nine timings**, rig 24e, three launches against a loopback deployment:

| | samples |
|---|---|
| `apg studio` start → the `open` line | 0.74 s, 0.66 s, 0.74 s |
| `GET /` with the cookie | 1.3 ms, 3.1 ms, 2.4 ms |
| `GET /__apg/schema` | 1.3 ms, 1.1 ms, 1.2 ms |

**The IR's counts as read**, from the served `/__apg/schema` payload rather than
recalled: **3 relations, 4 RPCs, 7 tools, 1 enum, 5,235 bytes**. The plan said
*“7 relations / 7 tools”*; 7 is the OBJECT count (3 + 4), which is how the
envelope's existing `apg generate` row for the same manifest states it, and
reading it is what settled the difference.

**A proof corrected by its own first run.**
`test_the_envelope_carries_studios_three_latencies` demanded a surface size from
all three rows, including the static page — which does not read the IR at all.
Satisfying it would have put a false relevance in the document, so the page row
names the bytes it serves and says *no surface size applies*, and the assertion
now asks each row for the size of the thing its number is actually about.

**The documents**: `docs/studio.md` 317 lines, indexed
(`test_documentation_index` green); `docs/threat-model.md` a Studio section and
a retention residual; `docs/scope-closure.md` §13, nine rows; `README.md` a
Studio section.

**Three edits moved to Run 6 rather than left red** (D1277): the threat table's
ROW, the README's *Session N implemented* line and its `template_version`, and
§1's counts. Everything that does not depend on a Run 6 constant is here.

### Run 6 — the bump

**Read first:** `docs/plans/session-23-implementation-plan.md` §5 Run 6 whole
(the shape this run copies step by step — every one of its Done paragraph's
finds was in that run's own tests: D1236–D1241); `bin/session-23-check.sh`
whole; `tests/contract/test_session_twenty_three_gate_modes.py` whole;
`tests/contract/test_offline_claims_are_swept*.py` or wherever D1240/D1242's
guard lives (`git grep -ln "p0 and not future and not live_host" -- tests`)
— **it checks the selector against the NEWEST gate script, so deriving
`session-24-check.sh` moves what it reads**; `.github/workflows/ci.yml` lines
236–290; `tests/deployment/test_session23_client.py` whole (the live module
this one copies: markers, the roster variables, `pytestmark`, the sweep in
`finally`); `tests/deployment/conftest.py` `audit_admin`, `admin_session`,
`create_reader` (Session 22's module), `mcp_rpc`, `app_login`, `api_call`.

1. `src/agentic_postgres/__init__.py`: `CURRENT_SESSION = 24`; `VERSION` →
   `1.5.0` with ADR 0162's pricing in the constant's comment (a new operator
   command, one released migration, one additive response member; no schema
   moves; a minor, confirmed by Run 7's `upgrade plan`). **Then regenerate
   the client in the same commit** (D1238: `contract.ts` carries
   `templateVersion`) and `generate --check` → 0.
2. `tests/acceptance-registry.yaml`: the eleven requirements of §2 with the
   node ids the runs actually wrote — **read each clause of each description
   against a node id** (D1236); `ID_PATTERN` gains `STU` with its reason;
   `evidence_claims.py`: the four claims, `OFFLINE_CLAIMS |=
   {"studio_boundary", "studio_surface"}`, the two host claims with the
   reason beside them; `bin/render-acceptance-matrix.py --write`;
   `test_acceptance_registry` and `test_evidence_claims` green (the
   per-session offline assertion, D1237).
3. **The live module** `tests/deployment/test_session24_studio.py`, marked
   `p0`, `security`, `live_host`, `requires_environment("APG_LIVE_HOST",
   "APG_PROJECT_A_OUTPUTS", "APG_ADMIN_PASSWORD_FILE")`:
   - `test_revocation_through_studio_refuses_the_agents_next_request_on_alpha`
     (`STU-REVOKE-001`): an audit-capable subject made as `audit_admin` makes
     one (its password in a 0600 file under `tmp_path`); an agent on alpha
     (`create_reader`'s shape, this module's own name, swept in `finally`);
     `list_resources` through `mcp_rpc` → served; Studio launched as a
     subprocess by the sweep's root with `--project` the checkout's
     `project.alpha.yaml` (the host manifest — **read where the trip scripts
     keep it and pass that path**; it is outside the checkout for gamma and
     inside for alpha/beta), `--outputs $APG_PROJECT_A_OUTPUTS`, the subject
     and file; the URL read; `/__apg/revoke` with the wrong confirm → 422
     and `list_resources` still served (the control); with the right one →
     200; `list_resources` → refused (`refused()` reads `isError` and
     `error`); `/__apg/audit?agent_id=<id>` → the refusal's row present with
     a non-null `denial_reason` — which is ALSO `AGT-AUDIT-002`'s live half,
     so the second proof:
   - `test_the_deployed_audit_read_carries_the_boundary_of_a_real_refusal`
     (`AGT-AUDIT-002`): the same row read DIRECTLY through `GET /admin/audit`
     with `api_call` (the product's endpoint, not Studio), `denial_reason`
     non-null and equal to what Studio showed; every `served` row in the
     page null.
   - `pytest --setup-plan tests/deployment/test_session24_studio.py` with
     the three variables SET: both collected, neither deselected; UNSET:
     both skip cleanly (D671, D676) — both outputs in the Done paragraph.
4. **CI**: nothing new — the runtime module is in the Session 2 job by its
   marks (D1240: assert it by running the sweep's selector over the new
   modules in `test_offline_claims_are_swept`'s shape, and read the count).
5. **The gate.** `bin/session-24-check.sh` **derived from
   `bin/session-23-check.sh` by diff** (D505, D507, D678, D693, D703, D1108,
   D1109): a derivation script whose every substitution is anchored to match
   exactly once; `readonly SESSION=24`; header and usage rewritten whole and
   **read line by line, both halves** (Session 23's derivation found two
   lines no substitution could). Offline mode: step 3's sweep now carries
   the four Studio modules by their marks (nothing to add); a new step
   **8c** *"Studio ships no third-party code"* running `python -m pytest -q
   tests/contract/test_studio_assets.py` (cheap, and the sentence in the
   gate's output is what an operator reads); the usage names the two
   offline claims and the two host ones. Host mode: unchanged in arguments
   (**no new flag**; the live module reads three declarations the gate
   already takes); prose says the sweep launches Studio as root on the host
   and that **`--mode host` now answers for Sessions 22, 23 and 24 at once**
   (D1244) — and step 9 writes the host half for `${SESSION}` only; the
   22/23 halves are the merge sheet's (Run 7 step 8). External: prose only.
   Session 18's five declaration flags stay (D1133). `SHELL_COMMANDS` gains
   it. Every `printf` whose format begins with `-` is `printf -- ` (D1199).
   `tests/contract/test_session_twenty_four_gate_modes.py` derived from 23's:
   `SESSION_TWENTY_FOUR_CLAIMS = {"offline": ("studio_boundary",
   "studio_surface"), "host": ("studio_revocation",
   "audit_boundary_reported")}`, the docker refusal, the offline half from
   step 3's JUnit, step 8c present by structure. **The selector guard
   (D1242) now reads `session-24-check.sh` as the newest gate** — run it
   and read that it did.
6. **Documents**: README's *Adopt `1.5.0`*; `docs/scope-closure.md` §1 and
   §13 finished; `docs/decisions/README.md` count; the matrix and the
   evaluation report regenerated where their inputs moved.
7. `bin/session-01-check.sh` once on the clean tree (D1239: if step 2 cannot
   reach PyPI from WSL, run that ONE step's command inside the pinned Python
   image as Session 23 did, and say so). Repair and re-run **only the module
   that failed**, then push.

**Targeted:** `test_evidence_claims`, `test_acceptance_registry`,
`test_cli_contract`, `test_capacity_envelope`, `test_documentation_index`,
`test_session12_documented_path`, `test_repository_contract`,
`test_gate_contract`, `test_session_twenty_four_gate_modes`,
`test_session_twenty_three_gate_modes` (its `SESSION_PREVIOUS` reads 22's; it
must still pass), the D1240/D1242 guard module, `test_compatibility`,
`test_upgrade_plan`, `test_upgrade_command`, `test_deployment_suite_shape`,
`test_generate_command`, `test_client_typescript`, then the gate. Push; read
CI.

**Done.** `CURRENT_SESSION` 24 and `VERSION` 1.5.0, eleven requirements, four
claims, the live module, `bin/session-24-check.sh` and its modes module.

**The node ids, as WRITTEN against as proposed** (D1236 — every clause checked
against a node id rather than copied). Three of §2's proposals do not exist:
`test_migration_contract.py::test_0032_reissues_the_reader_grant`, whose module
does not exist and whose proof is in `test_migrations.py` — D1264 from Run 2,
finally reaching the registry — and `test_database_function_signatures.py` and
`test_operator_commands_run_on_the_host.py`, both named without a node id, which
are `::test_every_call_to_a_released_function_uses_a_released_arity` and
`::test_operator_commands_import_only_host_packages`. Two proofs Run 4 wrote
have no place in §2 because §2 predates them, and both belong to
`STU-SURFACE-001`: the administrator's role-scoped surface (D1275) and the
ungated capability view (D1274). `test_the_rig_cost_is_recorded` is deliberately
unregistered — it records a number rather than asserting a property, and a
requirement naming it would be one satisfied by a `print`. **Eleven
requirements, 78 node ids.**

**The `--setup-plan` outputs, both ways.** Unset: `SKIPPED [2] … environment
absent: APG_LIVE_HOST, APG_PROJECT_A_OUTPUTS`, no error. Set: both tests
collected, neither deselected, six module fixtures set up and torn down in
order. The gate is on two declarations and not three, because the third is not
in `ENVIRONMENT_VARIABLES` and the marker refuses a name outside it (D1278).

**The derivation: 9 anchored substitutions, and the line-by-line read found 4
more blocks** no substitution could reach (D1279). One had become false rather
than merely stale — the host-mode precondition said this session *“adds NO
released migration”*, and 0032 is one. Twenty-four lines still carry a `23`, and
every one is a true reference to what Session 23 did.

**The gate**: 1,499 lines; `--help` exits **0** in 181 lines. Step 8c is the
only new step, and step 3's sweep already collects the asset module by its
marks — what 8c adds is the sentence an operator reads.

**The modes module found three more literals** (D1280), one a real defect: the
executable-bit test was `git ls-files`-ing the PREVIOUS gate. Derived from
`SCRIPT` instead, it went red immediately on the true thing — the new gate was
not in the index yet (D1188).

**The selector guard's reading**:
`test_the_offline_sweep_selector_is_the_newest_gates` finds the newest gate by
glob, so it now reads `bin/session-24-check.sh` and passes; and
`test_every_offline_claim_proof_is_collected_by_the_offline_sweep` passes with
the eleven new requirements in it. That is step 4's answer: the runtime module
is collected by the sweep that reports its claim, by its marks, with no CI
change at all.

**And D1237's repair was itself one scope too wide** (D1281). Session 23's
subtraction made *no later session may declare an offline claim* true again, and
Session 24 is the later session; both modules now match on their own session.

**The gate, and the one step this workstation cannot run.**
`bin/session-01-check.sh` on the clean tree reaches step 2 and dies there:
`bin/lock-dev-deps.sh --check` fetches from PyPI and WSL on this machine has
lost outbound HTTPS (D1239). That one command was run instead inside the Python
image `versions.env` pins **by digest**, with the checkout mounted and `uv` at
the `0.12.1` the script itself pins and refuses to run without — read out of
that script rather than retyped. It answers `requirements-dev.txt is current at
cutoff 2026-09-03T15:16:21Z`, exit 0. **The rest of the gate ran in CI**, whose
*Session 1 gate* job invokes exactly this script on a runner that has a network:
green at `f26e600`, alongside the Session 2 offline job's **5,685 passed, 3
skipped, 446 deselected** — with the Studio runtime module among them, which is
the reading Run 4's and Run 5's red CI was waiting for.

**And the fixture's warning did not fire there**, so the rig reached the cluster
at its published port. That rules out the mechanism D1276 proposed rather than
confirming it: the pool now connects after the network is joined and succeeds,
where before it connected first and was refused. What is established is that the
reading has to be taken in the topology the rig will use; the mechanism is not,
and the row says so instead of telling a tidy story (ADR 0195).

### Run 7 — the trip: three sessions' evidence, one sweep

**This run is the only one that touches the host.** Split as the memory
records (*host-trip-shape*): the agent runs every `op`-side step over SSH and
hands the operator a numbered sheet of `sudo` lines; the operator pastes
output; the agent reads. One 15-minute sweep, a second only if the first found
a defect. **Never redirect a sudo deploy** (D972).

**Before the day** (agent, offline):
- `grep -n "goes wrong" -A20` in `docs/session-11-operator-guide.md` and the
  Session 17, 18, 20, 21 plans (D977); Session 21's Run 7 Done paragraph
  whole (the last trip's shape and the eight minutes D1152 cost); Session
  20's D1116–D1120 (the four free gates).
- `pytest --setup-plan` for `test_session22_plane.py`, `test_session23_client.py`,
  `test_session24_studio.py`, `test_honest_readers.py` with the variables SET
  (D671, D676) — outputs kept.
- **Grep the tree for what the bump commit's message claims** (D1116):
  `git diff --stat main..session-24` against §5's list, one line each.
- Read the pushed branch head's CI verdict by full SHA (D1120). Green, or
  the trip does not start.
- Host scripts staged under `/home/op` (op-owned; survive a reboot), each
  with `export PATH="$HOME/.local/bin:$PATH"` and absolute paths, derived
  from Session 21's (`s21-checkout.sh`, `s21-renders.sh`, `g21-offline.sh`,
  `s21-upgrade.sh`, `s21-read.sh`, `s21-diag.sh`, `g21-host.sh`) by editing
  `EXPECTED=`, the session numbers and the gate name — **read each one
  first; the kernel restart may have happened and `/tmp/g20-sentinel.py`
  may be gone: rebuild the sentinel derivation from
  `bin/session-24-check.sh --help`'s block**. New this trip: `s24-plans.sh`
  (three `git worktree add` at `8823877e`, `2121c029` and the bump commit as
  op, `--render-only` in each, the three candidate documents copied to
  `/home/op/candidate-{13,14,15}.json`, the worktrees removed), and
  `s24-counts.sh` (the audit table counts, run by root through `docker
  exec … psql` on each project — D1255's number).
- The external script `/tmp/r7-external-24.sh` in WSL derived from
  `/tmp/r7-external-21.sh` (if `/tmp` survived; else from `bin/session-24-check.sh
  --help`'s external block), with an ephemeral `ssh-agent` and
  `--ssh-destination op@62.238.99.122` (D466).

**The day, in order.** `op` steps are the agent's over SSH; **`sudo` steps
are the operator's**, numbered on the sheet:

1. *(op)* `git bundle` of the branch head, `scp`, `git bundle verify`, fetch,
   `git rev-parse FETCH_HEAD` confirmed equal to the pushed SHA, checkout as
   `op`, `uv sync` (`--requirements` per D1023's lesson — read `README`'s
   materialize line). `s24-plans.sh` (the three candidates rendered).
2. *(sudo 1–3)* `bin/upgrade.sh check --project alpha-dev`; `plan --project
   alpha-dev --candidate /home/op/candidate-13.json`, `-14`, `-15` — **three
   verdicts recorded** (D1081: `minor` confirms 1.3.0, 1.4.0 and 1.5.0 in
   turn; a `major` on any is §9's stop). The same `plan` for `beta-dev` with
   `-15` only.
3. *(sudo 4)* `./deploy.sh --through-session 24 --project alpha-dev …`
   (the exact line from `deploy.sh --help` on the host — the agent prints it
   on the sheet), unredirected. Then *(sudo 5)* the read: the ledger via
   `bin/migrate.sh` (D941) → 32 applied, `0032` last; `auth` and `mcp`
   container ages seconds (ADR 0155); the doctor 10/10; `sudo cat` of the
   rendered lock's `tools_sha256`; `s24-counts.sh` alpha.
4. *(sudo 6–7)* the same on `beta-dev`: ledger → 34 (`0032` and the example
   set's `20260914120002`, D1189's repair — the FIRST deploy that applies
   it; read that `SET ROLE <authenticated>; SELECT count(*) FROM
   api.note_embeddings` now succeeds, the way the offline proof ends); the
   doctor 10/10; `s24-counts.sh` beta.
5. *(op)* `s21-read.sh`-style op-owned copies of both deployed documents
   fetched to WSL (`sudo install -o op` is *(sudo 8)* first). **D1164's
   confirmation**: `stat -c '%U %y' .generated/alpha-dev` on the host
   before and after the sweep (step 7) — the named suspect is
   `test_session13_upgrade_plan`'s `candidate` fixture.
6. *(op)* `bin/session-24-check.sh --mode offline` on the host as op
   (`g21-offline.sh`'s shape, edited) — the offline half FOR 24 written on
   the host too, as a control that the checkout there is the one measured
   here; then `--mode offline` for 22 and 23 is NOT run on the host: their
   offline halves already exist on this workstation at their own commits
   (ADR 0202: the merge prints the difference).
7. *(sudo 9)* **The one sweep**: `sudo bin/session-24-check.sh --mode host`
   with every declaration `--help` lists — the five Session 18 flags with a
   FRESH kit exported first (`bin/dr-kit.sh export`, *(sudo 8b)*, then
   `verify` from this checkout off-host: REC-KIT-003 as a reading), the
   sentinel derived, `--admin-password-file /root/alpha-dev-administrator`,
   both outputs. **Run it detached** (`setsid nohup … > /home/op/g24-host.txt
   2>&1 < /dev/null &`, the exit code written to a file by the script — the
   memory's rule). ~15 min. Expected: every Session 22, 23 and 24 host claim
   `passed` in the JUnit; the two root-run `test_honest_readers` proofs
   EXECUTED for the first time (D1165 — read their node ids in the JUnit:
   `passed`, not `skipped`); the four D1123 claims passed; the Session 23
   example client run in the toolchain image against beta (`ok`) and alpha
   (`stale_contract` naming both digests); `list_resources` on beta reporting
   the lock the plane confirmed. If a proof FAILS: read it, repair on the
   branch, CI, transport, redeploy only if the repair touches a container,
   and re-run **with `-k`** for that module (writes no evidence), then the
   sweep once more only if the repair changed what a claim reads.
8. *(op, then the workstation)* the host half copied to WSL; `--mode
   external` from the workstation (`/tmp/r7-external-24.sh`) → the external
   half. **Three merges, from a checkout at `main`'s head after the
   fast-forward** — or from the branch head, and the writer prints the
   difference for each offline half's `checkout_commit`:
   ```
   python bin/write-session-evidence.py --session 22 \
     --host-input evidence/session-24-host.json \
     --external-input evidence/session-24-external.json \
     --offline-input evidence/session-22-offline.json \
     --output evidence/session-22.json
   ```
   and the same with `--session 23 … --offline-input evidence/session-23-offline.json
   --output evidence/session-23.json`, and `--session 24 … --offline-input
   evidence/session-24-offline.json --output evidence/session-24.json`.
   **Measure first, on the 22 merge, that the writer ACCEPTS a host half
   written by the Session 24 gate for `--session 22`** — if it refuses
   (a session field in the half, say), the host half is re-derived by
   invoking the writer's half-writing step over the sweep's JUnit with
   `--session 22` (`write-session-evidence.py --session 22 --mode host
   --junit evidence/session-24-host-tests.xml [--junit …-claims.xml]
   --project-a-outputs … --project-b-outputs … --output evidence/session-22-host.json`
   — the gate's own step-9 invocation with the session number changed; read
   `bin/session-24-check.sh` step 9 for the exact arguments) and the same
   for 23; and the D row records which of the two it was. Expected in
   `evidence/session-22.json`: `plane_confirmed_count`, `agent_tenant_read`
   `passed`; in 23's: `generated_client_hash`, `agent_lock_reported`
   `passed`; in 24's: all four Session 24 claims `passed`, and the nine
   standing `not_run` of Session 21 reduced by `honest_readers` (its offline
   half is Session 22's D1165 repair, now executed as root).
9. *(sudo 10, optional)* the round trip by hand — because the gate's pass is
   a number and the trip's record is what the next reader reads: `apg
   studio` launched by the operator on the HOST as root against alpha (the
   administrator's password file, `--project /home/op/…` or the checkout's
   manifest), the URL opened in a browser through an SSH port-forward
   (`ssh -L 8765:127.0.0.1:<port> op@…` — the one time a browser sees the
   page; the forward is loopback-to-loopback, and this is what Studio's
   design permits), the schema, one query, the audit page showing the
   sweep's refusals with their boundaries, the agent list; then close. The
   operator's reading pasted; the session end line read. *Optional* because
   the claim is already measured; not optional to record if it happens.
10. D rows for what the day found; this run **Done.** with the three
    documents' claim tables pasted, the three `upgrade plan` verdicts, the
    two ledgers, the two audit counts (D1255), the D1164 owner/mtime
    reading; `CLAUDE.md` §2 rewritten (the launch folder's file — copy it
    to the scratchpad first) with a `SESSION 24 COMPLETE` block; memory;
    commit, push, CI; fast-forward to `main`; delete the branch.

**Done.** *(the day, in order, with every number; what the trip cost; what
it left.)*

---

## 7. Evidence and claims

A claim's verdict is computed from the registry's node ids and JUnit results,
never hand-entered; three statuses (ADR 0163); a skip is not a pass; a `-k`
run writes nothing; an offline claim is declared, never inferred (ADR 0202).
**This session's trip writes three merged documents** (D1244), and each
offline half names its own `checkout_commit`, which the writer prints beside
`source_commit` when they differ — recorded, never required, never hidden.

| Claim | Mode | Measured where | Expected at close |
|---|---|---|---|
| `studio_boundary`, `studio_surface` | offline | the gate's offline mode here and on the host; CI | `passed` in `evidence/session-24-offline.json` and in `evidence/session-24.json` |
| `studio_revocation`, `audit_boundary_reported` | host | Run 7's sweep on alpha | `passed` in `evidence/session-24.json` |
| `generated_client_hash`, `agent_lock_reported` (23's) | host | Run 7's sweep | `passed` in `evidence/session-23.json` (three halves: 24's host and external, 23's offline at `2121c029`) |
| `plane_confirmed_count`, `agent_tenant_read` (22's) | host | Run 7's sweep | `passed` in `evidence/session-22.json` (24's host and external, 22's offline at `8823877e`) |
| `honest_readers` | host + offline | Run 7's sweep as root (D1165's branch, first execution) | `passed` for the first time in both halves |
| the eight expected `not_run` (the five D478 names, `fresh_host`, `documented_path`, `replacement_host_restore`) | — | — | unchanged, with their reasons |
| every claim through 21 | host / external / offline | Run 7 | unchanged |

`evidence/session-24.json` is expected at **122 claims** (118 + 4), with the
`not_run` count **8** — Session 21's nine less `honest_readers`. A ninth is a
finding, not a footnote.

---

## 8. Security invariants this session touches

- **A human cannot run SQL through a product surface** (stage plan §8): the
  forwarder's table has no SQL and no free path; every REST operation is a
  `GET` built from validated parts; there is no RPC call in the table at all
  (a reviewed RPC is a write, and the query builder reads) —
  `test_the_forwarder_table_has_no_rest_write`,
  `test_rest_query_refuses_a_relation_a_column_or_an_operator_the_surface_does_not_name`.
- **PostgreSQL is the final authorization authority**: Studio sends the
  human's token and PostgREST applies RLS; Studio filters nothing by owner
  and adds nothing — `test_a_query_as_a_returns_as_rows_and_none_of_bs`.
- **The DX layer holds nothing the human does not hold**: a bearer and a
  refresh token in one process's memory, obtained by the human's own
  password; no key, no database credential, no provider token —
  `test_studio_holds_no_key_and_verifies_nothing`,
  `test_a_password_argument_or_environment_variable_is_refused`.
- **The page never holds the token**, and a hostile page cannot drive the
  process: `Host` (421), the launch cookie (401, `SameSite=Strict`,
  `HttpOnly`), `Origin` (403), the custom header (403), `OPTIONS` (405) —
  the seven `STU-BIND-001` proofs, and the CSP
  `default-src 'none'; script-src 'self'; style-src 'self'; connect-src
  'self'; img-src 'self'; base-uri 'none'; form-action 'none';
  frame-ancestors 'none'` with `Referrer-Policy: no-referrer`,
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Cross-Origin-Opener-Policy: same-origin`,
  `Cross-Origin-Resource-Policy: same-origin`, `Cache-Control: no-store` on
  every response — `test_every_response_carries_the_csp_and_security_headers`.
- **Loopback only, no switch** (D1245) —
  `test_the_listener_is_on_loopback_and_nowhere_else`,
  `test_there_is_no_bind_flag_and_the_address_is_a_constant`.
- **A revoked token stops on its next request, locally** (stage plan §8):
  revocation is the existing endpoint and nothing else; the typed
  confirmation is checked by the process —
  `test_revocation_through_studio_stops_the_agents_next_exchange` and the
  live proof on alpha.
- **No summarisation hides a denial** (D1248): the page is rendered whole,
  the boundary is a column, the header carries the page's own count —
  `test_the_audit_view_renders_every_row_of_the_page_with_its_boundary`,
  `test_a_view_filter_hides_no_row_from_the_pages_count`.
- **A refusal is classified, never relayed** (D433, ADR 0139):
  `test_an_upstream_refusal_is_classified_and_its_body_is_not_relayed`.
- **No record carries a URL, key, token or caller value** (the canary):
  `log_message` prints method, path-without-query, status —
  `test_nothing_studio_prints_is_a_token_a_key_or_a_value`.
- **A report may not substitute an answer** (ADR 0195): four surface
  answers; an undetermined own session reported and none ended; an
  `unreachable` upstream is `upstream_failed`, never `refused` —
  `test_unreachable_and_unreadable_are_two_answers`,
  `test_an_undetermined_own_session_is_reported_and_none_is_ended`.
- **No third-party code** (D1249) — `test_studio_assets_carry_no_third_party_code`.
- **An offline claim cannot report a live half** (ADR 0202): the two host
  claims are undeclared; the per-session assertion (D1237).
- **A released migration keeps every released arity** (ADR 0175): 0032's
  three arguments — `test_database_function_signatures`, run by name.

---

## 9. Stop conditions

- Rig 24b cannot start the auth application on a loopback socket against a
  dev cluster with the fixtures `test_auth_endpoints` already has: stop and
  read WHY before building anything on it — the offline runtime proof rests
  on it, and the fallback (a stand-in for the app) would prove the double,
  not the product. Do not write a proof that skips.
- The served document to the app-issued token does NOT equal the fixture
  snapshot's fingerprint in rig 24b: stop; rig 23a's equality held for a
  rig-minted token, and the difference must be understood (a role, a claim,
  a schema) before D1253's check is written against it.
- A Studio feature needs SQL, a non-loopback bind, or a credential beyond the
  human's (stage plan §9): stop; it is not a feature of this product.
- `CREATE OR REPLACE` turns out to accept the widened `RETURNS TABLE` at
  PostgreSQL 18.4: then 0032 uses it and the plan's DROP sentence is a
  divergence row — never both forms.
- `classify_changes` returns nothing for the regenerated client while the app
  digest moved (Run 2 step 3): a divergence row and a decision about the
  version rule, never a silent `1.0.0`.
- Run 7's `upgrade plan` prices ANY of the three candidates as **major**: a
  stop for that deploy, a row, and the operator's decision.
- The Session 24 host sweep's JUnit cannot be consumed by the writer for
  `--session 22` or `23` and the half-writing step cannot be invoked with a
  session number either: stop, record it, and run `session-22-check.sh
  --mode host` and `session-23-check.sh --mode host` as two more sweeps —
  the operator's call, with the cost named (D1244 was a plan, and the writer
  is the authority).
- A `test_honest_readers` proof still SKIPS as root in the sweep: read
  `_as_checkout_owner` first (a root-owned checkout takes the remaining skip
  branch by design); do not soften it.
- CI red on the branch: stop and read the log; a cancelled run is not a
  failed one (D1059).
- Docker absent in WSL: stop; do not write a proof that skips and call it
  offline evidence.
- WSL has lost outbound HTTPS on trip day: SSH still works (it is not HTTPS);
  the CI verdict is read through the Windows `gh`; the push goes through the
  Windows git over `//wsl$/` (memory: *where-it-lives*). Nothing in this
  session needs a registry.

---

## 10. Open items this session carries and creates

**Carried in, untouched:** D1045 (the provider error body); ADR 0197's
`fresh_host` and `documented_path`; `replacement_host_restore` (D1028); the
five D478 names; D1211 (PostgREST beside `apg dev` stays a rig — rig 24b is
its second instance and its cost is now measured twice); the four unswept
modules D1240 names (`test_database_function_signatures` is run BY NAME in
Run 2 and stays unswept — putting the storage three in a sweep is the
storage plane's decision); D1203; D1205; D1209; the 21 unclaimed
requirements (ledger §4).

**Stated here, not taken (the stage plan's two):**

- **The rotation performed (D860)** stays recommended and is NOT made a
  precondition by this session: Studio is a holder, not a verifier (D1246),
  so the key set has the same four verifiers it had. What the rotation
  proves (`bootstrap_identity`, `api_authorization`,
  `credential_rotation_planes`) still needs an operator sequence with an
  irreversible `promote`, and the recommended moment is any trip — this one
  included, if the operator chooses; the sheet does not include it.
- **The audit and idempotency tables' retention** (D1255): Run 7 records
  `SELECT count(*)` on both projects as the number a decision starts from.
  The decision is a released migration carrying a policy (a window, a
  ceiling, an archive), taken by whoever owns the compliance meaning of
  `agent_audit` — not a UI session. Studio's viewer is unaffected by the
  table's size because it shows the newest 500 and says so.

**Created here, not addressed:**

- **`/admin/audit` filters by agent, owner and limit only** (D1248). A
  server-side window (`since`/`before`), an outcome/boundary filter and a
  cursor are one migration (the reader's arity moves, so every call site
  moves — ADR 0175's guard finds them), one endpoint change, one contract
  recapture and one client regeneration. Priced, not built; Studio's view
  filters over the page it fetched and says what the page is.
- **Studio's own session id is inferred, not returned** (D1252): the login
  response carries no session id and Studio takes the newest live row after
  its login. An `X-Session-Id` (or a `session_id` member) on `/auth/login`'s
  response is one additive field; whoever adds it moves `own_session` to
  read it and keeps the inference as the fallback.
- **The launch URL is in the terminal's scrollback** (threat model §*Studio*):
  bounded by the process lifetime and the token's 900 s; the accepted
  residual, named.
- **Studio is single-user by construction**: one process, one token, one
  cookie. Two humans want two processes.
- **A browser on the host through an SSH forward** (Run 7 step 9) is the one
  path a person has seen the page on a deployment; it is loopback on both
  ends and is documented in `docs/studio.md` as the way to look, not as a
  deployment.
- **Rig 24b costs ~3 minutes in every offline sweep**, the second such rig
  (D1211). A shared session-scoped fixture serving both Session 23's and
  Session 24's runtime modules is one move (`tests/contract/conftest.py`
  does not exist yet; creating it is where the shared rig would live) and
  halves the cost; not done here because moving Session 23's fixture is a
  change to a passing module with no ADR asking for it.

---

## Appendix — what to consult, and how a run is executed here

**Consult, in this order.** `docs/plans/stage-3-plan.md` §5 *Session 24*,
§7, §8, §9, §10 and its rows D1069, D1074, D1079; this document's §1;
`docs/plans/session-23-implementation-plan.md` §1 rows D1200–D1211 (the
client's design decisions Studio's surface check copies), D1236–D1242 (what
the last session's runs cost, all in their own tests), its §5 Run 6 (the
bump's exact steps) and its appendix; `docs/plans/session-22-implementation-plan.md`
§1 D1172 (Docker's loopback publication) and D1199 (a gate's last lines);
`docs/scope-closure.md` §11–§12; ADR 0069, 0093, 0095, 0097, 0139, 0140,
0142, 0158, 0162, 0171, 0175, 0178, 0195, 0202, 0203, 0204;
`services/docs/serve.py` whole; `bin/api.py` lines 60–135; `bin/dev.py`,
`bin/dev.sh`, `bin/generate.py`; `tests/contract/test_generated_client_runtime.py`
and `test_auth_endpoints.py` (the two rigs 24b joins); `tests/contract/
test_dev_command.py`, `test_generate_command.py` (the command-proof shapes);
`tests/deployment/test_session23_client.py` and `test_session22_plane.py`
(the live-module shapes and helpers); `/tmp/r24a.py`, `/tmp/r24b.py`,
`/tmp/r24c.sql` in WSL with their `.txt` outputs after Run 1 — **copy them
to the scratchpad before the first `wsl --shutdown`**.

**How a run is executed in this repository** (the short form of `CLAUDE.md`
§1 and §5; read those, they are the record of what each of these cost):

- The Bash tool is Git Bash on Windows. The tree is in WSL:
  `wsl bash -lc "cd ~/projects/agentic-postgres && . .venv/bin/activate && …"`.
  Anything with nested quotes, `$VAR`, a heredoc or a loop variable goes in a
  script written with the Write tool to `\\wsl$\Ubuntu\tmp\x.sh` and run
  with `wsl bash -lc "bash /tmp/x.sh > /tmp/x.txt 2>&1"`, printing its own
  exit codes; read the output back through `\\wsl$\Ubuntu\tmp\x.txt`.
- **The venv does not install the package.** Every Python that imports
  `agentic_postgres` outside pytest needs `PYTHONPATH=src` (or
  `sys.path.insert(0, ".../src")`).
- File content and commit messages are written with the Write tool and read
  by the script (`git commit -F /tmp/msg.txt`). Never a heredoc for content.
- `chmod 755 bin/*.sh bin/*.py deploy.sh` before every `git add`.
- Never pipe a suite or a gate into `tail`; redirect to a file, `rm` it first.
  **Run a long gate detached** (`setsid nohup bash /tmp/x.sh >/dev/null 2>&1
  < /dev/null &`, the exit code written to a file from inside WSL) and never
  beside a CI watcher — the laptop is the machine that runs out of memory.
- `PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared before a battery;
  same-length rewrites within a second import stale bytecode (D1198).
- A run's commit: `ruff format && ruff check` (print the exit code), the
  targeted modules — each named module checked for existence individually
  (D1104) — the derived-document generators whose inputs moved, `chmod`,
  `git add -A`, commit with `-F`, push to `session-24`, then read that SHA's
  verdict: `gh api "repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40
  chars>" --jq '.workflow_runs[] | [.id,.status,.conclusion] | @tsv'`, judged
  on HTTP status, three buckets (D1059). **Read it every time** (D1120).
- **A commit message is not evidence that the diff contains what it says**
  (D1116): `git diff --stat` against the list of repairs it claims, one line
  each, before the message is written.
- A run that renames, removes or adds a test function puts
  `test_acceptance_registry` in its targeted list (D1119); one that adds or
  removes a `bin/` command puts `test_cli_contract` there (D1014) and
  `git add`s the command first (D1188); one that adds any `document[...]`
  read to a `bin/` command puts `test_container_selectors` there (D1184).
- **A run that MOVES a definition greps the moved TEXT as well as the moved
  name** (D1187).
- **The targeted list is run ONCE, at the run's close, scaled to the
  change.** After a failure re-run only the module that failed; CI is the
  full check (the operator has asked for this thirteen times). During a run,
  run the one module under the hand.
- **A targeted list is derived from the tree, never from the plan's text**
  (D1146, D1149): the lists above name what a run ADDS; the grep names what
  it CHANGES.
- Documentation-only commits run nothing before push. Generated content
  (the ADR index, the registry matrix, the envelope) → `bin/session-01-check.sh`
  alone. Code → the targeted modules. The gate on a clean tree at Run 6's
  close and on the host in Run 7, never at a run's close.
- A rig is a throwaway script with a control arm, its output in a file and
  its numbers pasted into the Done paragraph. Never write a measurement you
  did not run (D267). `docker rm -f -v` every container it started; `apg dev
  down` in `finally`; `docker ps -a | grep apg-` empty afterwards.
- The battery: every mutation's anchor pre-flighted to match exactly once
  and a miss fatal (D269); a paired control the mutation cannot reach, in
  the same invocation, green (D499); the reader distinguishes `FAILED` from
  `ERROR` (D386); restore by copy and `cmp`, never `git checkout --`; a
  survivor is evidence and is read as such (D493, D498); a scan over a file
  with comments strips them first (D1197). **Every new test module carries
  `pytestmark` before its first test** (D1240), and the D1242 guard is in
  the targeted list of every run that adds a module.
- **A proof calls the product's own command** (D1114, D1117): the runtime
  module runs `bin/apg.sh studio` and drives its loopback server the way the
  page does — not a Python re-implementation of the forwarder. The stand-in
  in `test_studio_server.py` is a double of an HTTP shape and its docstring
  says so.
- **Runs 1–6 touch no host.** No SSH, no `sudo`, no deploy. If a step seems
  to need one, it belongs to Run 7 and goes on the sheet.

**Grep the plans before measuring a third party.** `http.server`'s handler
attributes and `ThreadingHTTPServer`: `services/docs/serve.py` (D226, D128);
Docker's loopback publication: Session 22 D1172 and rig 22a; PostgREST's
JWT configuration: `compose.yaml:717-760`, `bin/render-jwks.py`, D186; the
auth app's settings: `test_auth_endpoints.environment` and
`services/auth-api/app/settings.py`; uvicorn in the tree: `git grep -n
uvicorn -- services tests bin` (the container's entrypoint is the only
production caller — copy its arguments); the session plane's rows and their
resolution: ADR 0171, `refresh_sessions.py`, D829 (no device stored); the
`--confirm` shape: `bin/edge.sh:300`, `bin/bootstrap-providers.sh:211`; the
canary's list: `services/auth-api/app/mcp_telemetry.py:13-25`. Nothing
indexes the ~1,250 measured facts by subject; `grep` is the index.
