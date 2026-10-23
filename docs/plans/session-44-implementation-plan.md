# Session 44 — The browser SQL editor: the customer's own client in the console, through a relay that holds nothing

**Status: COMPLETE — Runs 1–9 DONE (2026-10-23; rows D2759–D2807, ADRs 0285–0287; 1.22.0 tagged on 224b660 and published; NEXT FREE D2808, ADR 0288).** Planned at `8a594de` (Session 43's close, tree
clean, `main` = `origin/main`) against the host as read that afternoon (§0).
Rows **D2732–D2758** at planning; the runs add theirs from **D2759**. ADRs
**0285–0286** are Run 1's. **NEXT FREE after this table: D2759, ADR 0287.**

The ninth session of Stage 5 and the one the operator added on 2026-10-18
(D2592): the stage plan's *Session 44* brief (`docs/plans/stage-5-plan.md` §5
*Session 44*, `:994-1052`; *Builds* `:1016-1033`, *Already true* `:1035-1037`,
*Must not* `:1039-1042`, *Measures* `:1044-1047`, *Closes* `:1049`, *Proposed
family* `:1051`) — **a SQL editor in the console that is the customer's own
client: the customer's database password held only in the page, PostgreSQL's
protocol carried over a WebSocket to a relay that authenticates nothing, holds
no credential and reaches only a project's own public door names** — with **the
two choices the operator took at this planning on 2026-10-21** (§1 D2732, D2733),
and what Session 43 handed it (`docs/scope-closure.md` §36, *"What Session 44
inherits, in order"*, `:1749-1765`): **`site_live` re-earned** (D2728, the
recorder already repaired) and **the repinned Postgres image shipped** (D2731,
on `main` since `9fa9042`, undeployed).

Nine runs and **one sitting** on the host. **Run 1** is documentation, one agent
act on the Cloudflare zone (the relay's name), five rigs and two ADRs. **Runs
2–6** change code. **Run 7** is the bump. **Run 8** is the sitting: the release
on the four projects (the relay appears on `control-prod` only, and **every
project's database restarts once** — D2731's image, D2747), the dry runs, the
console walk again and the editor walk, **the sixth re-earning on a new
`slot8-prod`** (D2748), the sweep, the external half, the merge, the tag — and the
tag publishes `agentic-postgres-cli` 1.22.0. **Run 9** is the close.

**Brief:** `docs/plans/stage-5-plan.md` §5 *Session 44* (`:994-1052`); §6's row
(`:1099-1102`); §7's table row 44 (`:1146`); §8's invariants (`:1164-1193`, the
row *A product surface runs no SQL* `:1176`); §9's stops (`:1202-1246`, the 44
sentence `:1227-1229`); §11 (`:1297-1363`). `docs/scope-closure.md` §36
(`:1704-1765`). Session 43's plan §10, both lists
(`docs/plans/session-43-implementation-plan.md:2135-2183`), its rows
**D2714** (`:523`, why every new release re-earns the lifecycle), **D2715**
(`:524`, why a new external module and its roster entry land with the gate),
**D2725–D2731**, and its Run 10 (`:1838-1968`, the sitting to copy). ADRs
**0070** (the connection budget), **0167** (the edge proxy's alias on every
project network), **0195**, **0246** (the hosted boundary, the sentence this
session amends, `:91-99`), **0268** (the public Postgres door — read whole),
**0269** (the customer roles), **0276** (idle sleep), **0280** (the console and
its CSP constant, `:85-100`, `:147-149`), **0281** (its session cookies),
**0282**. `docs/product-contract.md` §5 (`:602-633`, the sentence `:631-633`).
`docs/reality-ledger.yaml` rows `sql_editor` (`:988-1003`), `console`
(`:214-255`), `wake_on_connect` (`:620-637`). `docs/threat-model.md` (`:17-74`
the table, `:190-459` the hosted list).

**Shape:** nine runs. **Run 1** reads **no** CI verdict (documentation; the zone
act and the rigs are recorded in its `**Done.**`). **Runs 2–6** each push and
read that commit's own CI verdict by full SHA (`gh api
"repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" -R
Virabyan99/agentic-postgres --jq '.workflow_runs[] | [.name, .status,
.conclusion] | @tsv'` from Git Bash, never inside `wsl`; judged on HTTP status,
three buckets — success / failure / not registered; an empty list is not a
verdict, D1057). **Every push to `main` also starts the `site` workflow after
`contract` succeeds** (ADR 0283): its line is read from the same listing.
**Run 7** is the bump. **Run 8** is the sitting. **Run 9** is the close (Ledger
and envelope rows are code: it reads CI). **Push only after the previous
commit's CI lands** — `ci.yml` cancels in-progress runs on `main`
(`.github/workflows/ci.yml:36-38`).

**Product version at close:** `CURRENT_SESSION` **44**; `template_version`
**`1.22.0`** — predicted *minor* (**no** project-manifest, outputs, host or lock
schema change, no new secret, no released or control-set migration; one new
compose service under a facility profile on the control project only; one new
image `services/sql-relay/`; a changed console environment and policy; **the
Postgres image's digest moves** — D2731's apt pins, `image_digest`) and **read
from `upgrade plan` on the host, never chosen** (Sheet R1). Released migrations
stay **39**; the control set stays **9**. **One new compose service
(`sql-relay`, profile `sql-relay`, control project only), one new image, one new
grey DNS record (`sql.agenticpostgresql.com`), one new certificate by the edge's
existing resolver. No new published port, no edge entrypoint change, no edge
recreate, no new `bin/` command.** A `major` is §9's stop.

**Written for whoever picks this up cold, and it will be a different model than
the one that planned it.** Every path below was read from the tree on 2026-10-21
at `8a594de` — three explore passes (the public Postgres door and everything
around it; the console, its guards and every reader of *SQL editor*; the
registry, claims, gates, Ledger, threat model, envelope and locks) and direct
reads of `bin/edge-network.sh:38-50,110-170`, `src/agentic_postgres/host_config.py:291`,
`tests/external/test_session43_console.py:205-220`, `bin/cloud.py:985-1010`,
`tests/contract/test_site.py:160-170`, `infra/edge/traefik.yaml:94-117` —
**and the readings taken at planning** (§0). Every path is cited `path:line`.
**Read CLAUDE.md §1 in the launch folder before the first command, then this
plan's §1, then the appendix.** If a step here and the tree disagree, **the tree
wins and the disagreement is a divergence row** (next free `D` after §1's
table), never a silent reconciliation. **When this plan names a line number,
open the file at that line and read the surrounding twenty lines before
editing** — the numbers were right on 2026-10-21 and `ruff format` moves them.

**The twelve sentences the executor most needs, in case nothing else is read:**

1. **The editor is the customer's own client, written here**: a small
   PostgreSQL wire-protocol client `services/console/public/pg.js` (startup,
   SCRAM-SHA-256 through WebCrypto, the simple query protocol, cancel) running
   in the console page, holding the customer's password in a closure only —
   never storage, never a URL, never a request to `/v1`. **No third-party
   script** (D2596 holds; the operator, D2732).
2. **The browser never sends the password anywhere.** SCRAM proves it; the
   relay and the door see the SASL exchange, never the password. The console's
   passwords are 32 random bytes (`scram.js:13`, `bin/cloud.py:1043`), so a
   captured exchange admits no practical guess (THR-SQL-READ).
3. **The relay is its own bounded service on its own name**,
   `wss://sql.agenticpostgresql.com` (the operator, D2733): a new image
   `services/sql-relay/` (Python, the `websockets` library pinned the way the
   auth image pins `segno`), a `sql-relay` compose service under a FACILITY
   profile added only for the control project (the `console` shape,
   `bin/project-runtime.sh:129-133`), routed by
   ``Host(`sql.agenticpostgresql.com`)`` on `websecure` with the baseline chain.
   **The browser never sends the console's `__Host-` cookies to it** (another
   host).
4. **The relay authenticates nothing and holds nothing** (no secret, no mount,
   no `/v1` call): it admits an upgrade only from the console's `Origin`, only
   for a path naming a public door host in the grammar `naming` derives (D2740),
   only inside its ceilings (D2741) — then opens **SSLRequest + TLS to the
   edge's own Postgres entrypoint** at `apg-edge-proxy:8432` (ADR 0167's alias,
   `host_config.py:291`) **with SNI = that name, ALPN `postgresql`,
   verify-full** (D2739). The edge's `sniStrict` routing decides the rest, as for
   any public client.
5. **The relay can read the protocol it carries** (SQL text, result rows, the
   SASL exchange) — the operator's choice (D2732): TLS on both hops, plaintext
   in the relay's memory only. **It writes none of it anywhere**: one log line
   per session (id, door host, outcome, close code, seconds, bytes), a canary
   proved offline and **live** (a marker string the walk sends inside a SQL
   comment is read absent from the relay's logs on the host, D2743).
6. **ADR 0285 amends ADR 0246's sentence** (and `docs/product-contract.md`
   `:631-633`) to: *"no product surface runs SQL on the platform's side or holds
   a credential that opens a project's data; the console may host the
   customer's own client, which speaks with the customer's own credential
   through a relay that holds none and records none of what it carries"*, and
   **amends ADR 0280's CSP constant**: `connect-src 'self'
   wss://sql.agenticpostgresql.com`, the relay's origin RENDERED, never typed
   (D2744).
7. **PostgreSQL decides**: the role's grants, row-level security and its
   `CONNECTION LIMIT` (2/2 on `standard`, ADR 0269) — and **there is no
   `statement_timeout` on the customer roles** (D2735, the brief's premise is
   false). The editor cancels a statement at 60 s or on the person's click (a
   CancelRequest through the relay — encrypted, the only cancel the door passes,
   ADR 0268 `:97-100`); the relay closes any session at 30 min. Neither changes
   what `psql` gets.
8. **The editor adds no claimant to ADR 0070's budget** (D2736): a session is a
   client of the existing pooled or direct door, counted against the role's
   limit exactly as `psql` is. The relay's ceilings are client-side: 32 sessions,
   4 per door host, 4 per source.
9. **A sleeping project is answered *asleep* by the page before any socket**:
   the page reads `GET /v1/projects/{key}` (`state`) first. A door the relay
   cannot reach closes with **4502 *"could not reach the database"*** — never
   *asleep*: a sleeping door and a wrong name fail identically in the TLS
   handshake (ADR 0268 `:68,73`), so only the control API can say *asleep*
   (D2737, ADR 0195).
10. **The editor is offered where the project has doors**: it reads `GET
    /v1/projects/{key}/connections` and uses that answer's `host`, `user` and
    `database`; a `409 not_available` is the page's existing *not available*
    text (D2738). Branch doors are not listed in this session (§10).
11. **The release restarts every project's database once** (D2747): `main`
    carries D2731's apt repin, a new Postgres image. **And it re-earns the
    lifecycle on a new `slot8-prod`** (D2748, D2714's mechanism) **and re-runs
    Session 43's console walk** (its record is pinned to the release commit,
    `test_session43_console.py:210-216`, D2749) before the editor walk.
12. **The `sql_editor` row moves `planned` → `trial` at the bump (Run 7) and →
    `beta` at the close only on its claims** (ADR 0261). Until the bump the
    editor view lands behind the Ledger guard's named exception, as the console
    did (D2746).

---

## 0. Where the session starts

```
HEAD            8a594de992d037000c448bff1ccdd9d79104cdd0 on main, local = origin
                ("docs(session-43): Run 11 done -- Session 43 COMPLETE"), tree
                clean. Code: 9fa9042 (the apt repin, D2731; contract 39622093716
                success, site 39626122578 success). Deployed AND TAGGED: 012ac06
                (1.21.0, tag object 70d9b47) on all four projects. main is 4
                commits past the tag: 244fd8d, 4da074d (the close: Ledger,
                Recorder User-Agent, envelope), 9fa9042 (a DIFFERENT Postgres
                image), 8a594de -- NOT deployed.
VERSION         1.21.0 (VERSION; template_version() src/agentic_postgres/
                __init__.py:1343-1349). CURRENT_SESSION 43 (:1335; Session 43's
                paragraph :1271-1334 -- its :1304 still says the console row is
                `trial`, true at 43's bump, `beta` since its close).
                README.md:7 "Session 43 implemented", 1.21.0 (guarded by
                tests/contract/test_documentation_index.py:170-212). Outputs 22,
                project manifest 1-11, host.yaml 2|3|4, 39 released migrations,
                the control set 9.
REGISTRY        415 requirements (tests/acceptance-registry.yaml, 8,300 lines;
                Session 43's block :8032-8300, `grep -c '^- id: '`). ID regex
                tests/contract/test_acceptance_registry.py:128 (alternation ends
                ...|PLAN|USE|INS|CON|SITE; Session 43's comment :126-127). **No
                `SQL-` id and no `SQL` prefix.** 322 claims (src/agentic_postgres/
                evidence_claims.py CLAIMS :565-1530, Session 43's block
                :1003-1027); 149 offline (OFFLINE_CLAIMS :106-518, Session 43's
                :484-516). CLAIM_INTRODUCED_IN tests/contract/
                test_evidence_claims.py:953-1365 (43's :1308-1327). 284 ADRs
                (docs/decisions/README.md last row :350 = 0284). NEXT FREE:
                D2732, ADR 0285.
EVIDENCE        evidence/session-43.json (WSL, gitignored): 322 claims, 320
                passed, 2 failed -- documented_path (D1935), site_live (D2728).
LEDGER          docs/reality-ledger.yaml (1,235 lines, 43 rows): beta 25, planned
                9 (wake_on_connect, email, passkeys, sql_editor -> 44,
                project_isolation, agents, workflows, connectors, audit),
                not_offered 8, not_metered 1, trial 0. schemas/reality-ledger.
                schema.json target_session maximum ALREADY 45 (:127).
GATES           bin/session-43-check.sh 2,247 lines (readonly SESSION=43 :104;
                usage :184-976; mode_offline :1699-1916, mode_host :1918-2136,
                mode_external :2138-2236; --console-record-file :180, :1184-1188,
                :2168-2169, :2195). tests/contract/test_session_forty_three_
                gate_modes.py 1,126 lines (SESSION = 43 :56,
                SESSION_PREVIOUS_NUMBER = 42 :71, claims :82-). SHELL_COMMANDS
                tests/contract/test_cli_contract.py:42-290 (session-43 :269).
                The environment roster tests/conftest.py:86-232 (last entry
                APG_CONSOLE_RECORD_FILE :231).
THREATS         docs/threat-model.md 485 lines: the THR table :21-74 (54 rows,
                the newest THR-CON-XSS ... THR-CON-GUESS :69-74 -- THR-CON-XSS
                already names "from Session 44 a database password in the page");
                the hosted list :209-459, items 1-21 (13 twice, D2673), item 21
                :452; the move-into-the-table rule :198-201.
ENVELOPE        src/agentic_postgres/capacity.py ENVELOPE :113-2475 (Session 43's
                section :2337-2474, seven measurements); UNMEASURED :2484-2566
                (seven).
HOST            15.204.231.45 (apg-ovh-01), read 2026-10-21 15:35Z (p1-p3).
OPERATOR        2026-10-21 (this planning): the in-house wire client, the relay
                reading the protocol (D2732); the relay on its own name
                sql.agenticpostgresql.com (D2733).
```

**What exists, measured at `8a594de`, and the session builds on:**

- **The public Postgres door** (ADR 0268, read whole). The edge is Traefik
  **3.7** (`versions.env:26`, `TRAEFIK_VERSION=3.7` `:72`; measured 3.7.10 in ADR
  0268 `:56`). A fifth entrypoint `postgres` on `:8432`, `readTimeout: 10s`,
  published `5432:8432` (`infra/edge/traefik.yaml:113-117`,
  `infra/edge/compose.yaml:136-139`); the TLS option `postgres`
  (`infra/edge/dynamic/baseline.yaml:31-35`: `minVersion: VersionTLS12`,
  `sniStrict: true`, `alpnProtocols: [postgresql]`; *"A client offering no ALPN
  (node-pg, Prisma) is unaffected"* `:28`). **TLS terminates at Traefik**; the
  PgBouncer behind it speaks plaintext on the project's `edge` network
  (`src/agentic_postgres/runtime_override.py:1069-1070`). TCP routers are labels
  on two services per slot, `_customer_tcp_labels` (`runtime_override.py:1064-1090`:
  ``HostSNI(`${CUSTOMER_POOL_HOST}`)`` / `…DIRECT…`, `tls.options=postgres@file`,
  one certificate naming both hosts, service port `6432`). `customer-pool`
  (`compose.yaml:761-842`; `pool_mode = transaction`, userlist `customer_app`
  only, `max_client_conn = 100`, `track_extra_parameters = search_path`,
  `server_reset_query_always = 1`, `:798-819`) and `customer-direct`
  (`:844-924`, `pool_mode session`, `customer_admin` only), profile
  `public-endpoints` (`:767`; `bin/project-runtime.sh:126-128`). **No
  `query_timeout`, `client_idle_timeout` or `server_idle_timeout`** on either.
  ADR 0268's measured refusals: no or wrong SNI → *"unexpected eof while
  reading"* (`:68`); a stopped backend refuses **exactly like a wrong SNI**
  (`:73`); `channel_binding=require` refused (`:69`); plaintext refused after
  11.4 s (`:70`); **psql's Ctrl-C cancel did not cross; psycopg's encrypted
  `cancel_safe()` cancelled in 3.0 s** (`:74`, `:97-100`). *"No product-owned TCP
  proxy is built"* (`:104-128`). *"Wake-on-connect is not built"* (`:177-180`).
- **The door's names** — `naming.endpoint_hosts(domain)` → `(pool.<domain>,
  direct.<domain>)` (`src/agentic_postgres/naming.py:553-568`);
  `naming.branch_endpoint_hosts(domain, branch)` → `<branch>.pool.<domain>`,
  `<branch>.direct.<domain>` (`:1112-1126`); `PUBLIC_POSTGRES_PORT = 5432`
  (`:545`); `PUBLIC_POSTGRES_SSLMODE = "verify-full"` (`:550`). The edge
  answers on every project's `edge` network as **`apg-edge-proxy`**
  (`host_config.EDGE_PROXY_ALIAS`, `src/agentic_postgres/host_config.py:291`;
  registered by `docker network connect --alias`, `bin/edge-network.sh:41-50`,
  `:163`; guarded twice-written by
  `test_the_edge_proxy_alias_agrees_between_the_shell_and_the_module`, ADR 0167).
  The postgres entrypoint's port inside the edge: `host_config.py:314-319`
  (`postgres`, 8432; public 5432).
- **The customer roles** (ADR 0269): only `customer_app` and `customer_admin`
  (`naming.py:190-196`; full name `apg_<key_sql>_<suffix>`, `:1184-1192`); `LOGIN`
  and `CONNECTION LIMIT` only when public endpoints are on, **never a customer
  `PASSWORD` from the bootstrap** (`docs/decisions/0269-…md:84-91`;
  `bin/postgres-bootstrap.py:493-526`); grants `bootstrap_statements.py:465-498`
  (the app: `USAGE` on `public`, DML by default privileges; the admin: `USAGE,
  CREATE` on `public`; both `USAGE` on `extensions`; neither on `app_private`),
  read back by `customer_violations` (`bin/postgres-bootstrap.py:529-595`). The
  claimants **small 2/2, standard 2/2, large 5/5**, equal to each role's
  `CONNECTION LIMIT` (ADR 0269 `:110-115`); the budget's sum
  `config._validate_connection_budget` (`src/agentic_postgres/config.py:1599-1679`);
  `max_connections` small 48 / standard 56 / large 100
  (`services/auth-api/app/compute_profiles.py:45,58,71`); **rig 39e: standard fits
  2/2, 3/3 leaves 15** (ADR 0269 `:74-78`). **`statement_timeout`**: set only on
  `app_runtime` (30 s) and on roles a manifest names
  (`rendering.py:208`, `:309-321`; `bootstrap_statements.py:330-334`); **the slot
  manifest names none** (`src/agentic_postgres/slot.py:163-179`).
- **Sleep** (ADR 0276): `GET /v1/projects/{key}` answers `state` among
  `creating, ready, suspending, sleeping, starting, updating, deleting, deleted,
  unknown` (`services/auth-api/app/control_states.py:39-69`;
  `control_service.py:1213-1231`); `POST /v1/projects/{key}/wake`
  (`control_routes.py:904-918`). A sleeping project's poolers are stopped, so
  its names refuse in the handshake. **An editor session through a customer door
  is customer activity and keeps the project awake** (ADR 0276 `:84-89`).
- **The connections answer**: `GET /v1/projects/{key}/connections`
  (`control_routes.py:1026-1049`; viewer and above, or a key with
  `projects:read`; `409 not_available` naming `pooled_endpoint` when there are
  no doors) → `{project, pooled: {host, port, user, database, sslmode,
  connection_limit}, direct: {…}, password: "<password from your file>",
  snippets}` (`control_service.py:807-820`, `DOOR_MEMBERS` `:117`).
- **The console** (ADR 0280–0282; `services/console/`, 9 files):
  `serve.py` (201 lines) — `ROUTES` `:44-52` (`/console/`, `/accept`,
  `/console/app.css|app.js|api.js|scram.js|pages.json`), `ENV_PATH
  "/console/env.json"` `:55` answering `{"api": API_PATH}` `:150-156`,
  `REDIRECTS` `:59-62`, `HEALTH_PATH` `:64`, **`CONTENT_SECURITY_POLICY`
  `:71-83`** (`default-src 'none'; script-src 'self'; style-src 'self'; img-src
  'self' data:; connect-src 'self'; font-src 'none'; base-uri 'none';
  form-action 'none'; frame-ancestors 'none'`), `SECURITY_HEADERS` `:85-95`,
  `log_message` naming no header and no query `:112-117`, GET/HEAD only
  `:171-175`, environment `APG_CONSOLE_PUBLIC`, `APG_CONSOLE_PORT`,
  `APG_CONSOLE_API_PATH` `:32-34`. `public/api.js` (73 lines) — *"The ONLY file
  that calls fetch"* (`:3`); `X-Apg-Console: 1`, `credentials: "same-origin"`,
  `redirect: "error"` (`:36-44`). `public/scram.js` (60) — `newPassword()` 32
  bytes `:29-31`, `verifier()` `:42-60`. `public/app.js` (817) — `once()` the
  shown-once widget `:101-108`, `connectView` `:400-440`, `frame` `:332-340`,
  `projectNav` `:342-346`, `VIEWS` `:758-770`, `route()` `:772-810`.
  `public/pages.json` (141) — 15 views, each with `ledger` and `calls`. The
  service: `compose.yaml:1225-1275` (profile `console`, `read_only`, uid 65532,
  network `edge` only; environment exactly the port and the API path), limits
  `config.py:759,798` (64 pids, 0.25 CPU, 192 MiB); rendered `APG_CONSOLE`,
  `APG_CONSOLE_ORIGIN`, `CONSOLE_ROUTER_NAME` (`rendering.py:2260-2262`, the
  `control` switch `:2253`); labels `_console_labels`
  (`runtime_override.py:1539-1558`; `CONSOLE_RULE_PATHS` `:265`; baseline chain,
  **no buffering, no strip**); `bin/deploy-project.py:460-470`
  (`_override_console`); `bin/project-runtime.sh:129-133`.
- **The console's guards this session meets** (every one changed only under
  ADR 0285, D2745): `tests/contract/test_console_server.py` — the literal
  `POLICY` `:33-37` asserted equal to the constant `:106` and on every answer
  `:117`; `LISTED == tuple(serve.ROUTES)` `:38-46,90`; `public/` holds only the
  ROUTES' files `:192-194`; every import a ROUTE `:151-171`.
  `tests/contract/test_console_scram.py:84-85` `names == ["api", "app",
  "scram"]`. `tests/contract/test_console_pages.py` — `SQL` regex `:30-35`,
  `test_no_script_holds_sql` `:98-103`, `test_no_script_writes_storage` `:106`,
  `test_only_api_js_calls_fetch` `:124-129` (**`new WebSocket` is checked by
  nothing**). `tests/contract/test_console_plane.py` — the rule's three paths
  and one router `:31-34,111`; the console environment exactly two names `:122`;
  no volume, secret, env_file, port or depends_on, networks `["edge"]`
  `:126-128`. `tests/contract/test_reality_ledger.py:251-280`
  `test_every_console_page_maps_to_a_reachable_row`.
  `tests/contract/test_site.py:165` uses `sql_editor` as its example of an
  unreachable row. `tests/external/test_session43_console.py` reads the console
  policy from `serve.py` (`_console_policy` `:92-100`), so it follows a changed
  constant by itself — **and pins its walk record** to `(43, "live")` and the
  control project's `source_commit` (`:210-216`).
- **ADR 0246's sentence** (`docs/decisions/0246-…md:94-99`): *"**a product
  surface runs no SQL** — the console, Studio, `/api/v1`, MCP, a workflow and a
  connector. A customer's own client, with the customer's own database
  credential, may; an agent never does."* — and `:91-93` (*the control plane
  holds nothing that opens a project's data plane*). `docs/product-contract.md`
  `:631-633` repeats it; `:619` keeps *"Arbitrary SQL execution by an agent,
  under any authentication"*. **ADR 0280 `:147-149`**: *"Session 44's editor
  joins the console under this policy and will need `connect-src` for its
  relay's `wss:` origin. That session's ADR amends this constant."* ADR 0281
  `:92-94`: *"Session 44 puts a database password in this page."*
- **The edge's HTTP side**: `websecure` `:8443` with `respondingTimeouts`
  `readTimeout 30s, writeTimeout 30s, idleTimeout 60s`
  (`infra/edge/traefik.yaml:94-100`); **no `forwardedHeaders` setting** on any
  entrypoint (`grep -n forwardedHeaders infra/edge/traefik.yaml` → none); the
  baseline chain `apg-baseline` = security headers, response policy, rate limit
  20/s average burst 40 per source (`baseline.yaml:42-58,80-94`); the access log
  drops `Authorization` and `Cookie`. **Nothing in `infra/`, `runtime_override.py`
  or `services/` has ever carried a WebSocket** (`mcp_origin.py:59`: *"There is
  no websocket surface here"*). Label routers only (ADR 0085), each container
  `apg.traefik.scope: managed` + `traefik.docker.network`.
- **How a Python service image pins a dependency** (the auth image's `segno`,
  Session 43): a `registry: pypi` entry in `versions.in.yaml` `packages:` (from
  `:216`; `SEGNO_VERSION` `:460-467`), `bin/lock-versions.sh --update` writes
  `versions.env` (`SEGNO_VERSION`/`…_DIGEST` `:63-64`); the Dockerfile declares
  the `ARG` with no default and runs `pip install "pkg==${VER}"` then an import
  self-check (`services/auth-api/Dockerfile:10-32,75-93`); compose passes
  `${VAR:?required}` (`compose.yaml:1515`). **`websockets` is in the tree only as
  a dev transitive** (`requirements-dev.txt:1373`, `websockets==17.1` via
  `fastmcp-slim`).
- **The apt pins D2731 moved** (`versions.env:33-34`, `:45-46`; comments
  `versions.in.yaml:576-603`, `:616-642`): `CA_CERTIFICATES_APT_VERSION=
  20250419~deb12u2`, `PGBACKREST_APT_VERSION=2.59.3-1.pgdg12+1`. **Both pins have
  an end date**; the comments say how to read the indexes.
- **The trip's tools from Session 43** (WSL, read 2026-10-21): `~/s43/run8/`
  (the instruments: `s43-window.py`, `s43-after.sh`, `s43-walk.py/.sh`,
  `s43-lifecycle.py`, `s43-branches.py`, `s43-sweep.sh`, `s43-external.sh`,
  `s43-hostyaml.py`, `s43-dns.sh`, `s43-r2shape.py`, …), `~/s43/run10/`
  (`NOTES.md`, `life-start.sh`, `br-*.sh`, `tag.sh`), `~/s43/run11/` (the gate
  shards); the pinned Playwright image is **present** in the workstation's
  Docker (`mcr.microsoft.com/playwright/python`, 3.47 GB unpacked);
  `~/s39/run11/creds/slot3-prod/` (0700, three 0600 files — `customer_app`
  W1's, `customer_app.before-s43`, `customer_admin`); `~/s37/probe.json`,
  `probe-password`, `probe-otpauth` (the probe owner of `probe-s37`, which holds
  `slot3-prod`).

**Measured at planning** (2026-10-21; no rig was run — every third-party fact
the build relies on is Run 1's, §5):

| # | Reading | Result |
|---|---|---|
| p1 | `apg-diag containers` (agent, 15:35Z) | exit 0; **47 containers**: alpha-dev ×10, beta-dev ×10, control-prod ×11 (the console among them), slot3-prod ×12 (`customer-pool`, `customer-direct` healthy), the plane's four (gateway `Up` with no healthcheck, the rest healthy); no branch |
| p2 | `apg-diag listeners` | 22, 80, 443, 5432 (+ the resolver's 53, chrony 323, DHCP 68) — unchanged since Session 42 |
| p3 | op: checkout, status, `free -m`, `uptime`, units, op copies | `012ac069b5bd16df629bdb69a62f1094d73f5ed2` clean; total 11,671, **available 8,224 MiB**; up 5 h 17; the reconciler, the edge and the telemetry units `active`; `/home/op/*-outputs.json`: alpha, beta, control-prod, slot1–7, snippets |
| p4 | `openssl s_client` (WSL, OpenSSL 3.5.5) to `pool.slot3.agenticpostgresql.com:5432`: (q1) `-starttls postgres` SNI the name; (q2) direct TLS, `-alpn postgresql`; (q3) direct TLS, no ALPN; (q4) `-starttls postgres`, SNI `unknown.agenticpostgresql.com` | q1–q3 **TLSv1.3, certificate `CN=pool.slot3.agenticpostgresql.com`, Verification: OK** — the door takes the SSLRequest AND direct TLS, with or without ALPN; q4 (the control) **`unexpected eof while reading`**, rc 1 |
| p5 | `curl` with a named User-Agent | `https://agenticpostgresql.com/` 200, CSP `… connect-src 'none' …`, `server: cloudflare`; `https://control.agenticpostgresql.com/console/` 200, CSP exactly ADR 0280's; `/` 301 |

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `8a594de`** (or the
host and the door as the planning readings left them) set against what the brief
says, with the decision this plan takes. **Next free number after this table is
D2759.** Rows the runs add go in a second table below it, in execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2732** | Stage plan `:1018-1022`: *"whether the browser driver can keep PostgreSQL's own TLS inside the WebSocket, so the relay sees only ciphertext (measured, never assumed — if it cannot, the plan says what the relay can read and the ADR decides); the browser driver pinned."* | Nothing in the tree speaks PostgreSQL's protocol in a browser. WebCrypto exposes no TLS; TLS inside a WebSocket needs a JavaScript TLS 1.3 implementation — third-party code (D2596 refuses any third-party script in the console) or one written here (unreviewed cryptography). **"PostgreSQL's own TLS" is the edge's**: the door terminates TLS at Traefik (`runtime_override.py:1069-1070`; p4: the certificate is the edge's). | **The operator, 2026-10-21: an in-house wire-protocol client, and the relay reads the protocol.** `services/console/public/pg.js`: StartupMessage (protocol 3.0; `user`, `database`, `application_name=apg-console-editor`), SASL **SCRAM-SHA-256** only (client-first with a 18-byte nonce from `crypto.getRandomValues`, client-final by WebCrypto PBKDF2/HMAC/SHA-256 — the primitives `scram.js` already uses — **and the server signature verified before `AuthenticationOk` is accepted**; any other authentication request refused), the **simple query protocol** only (`RowDescription`, `DataRow` text format, `CommandComplete`, `EmptyQueryResponse`, `ErrorResponse`/`NoticeResponse` fields, `ParameterStatus`, `BackendKeyData`, `ReadyForQuery`; `CopyInResponse` answered with `CopyFail`, `CopyOutResponse` read and dropped with a notice), and a **CancelRequest** sent as its own relay session (D2754). **TLS on both hops**: the browser → `wss://` (Traefik) → the relay; the relay → SSLRequest + TLS → the door (D2739). **The relay process holds the plaintext protocol in memory and records none of it** (D2743). Rig 44b measures every message against PostgreSQL 18.4 through PgBouncer; **no third-party file enters the console** (D2596 unchanged). | The page that holds the password stays free of code nobody here reviewed; the relay is our own process on the host whose root can already read every database, so its reading adds no new reader. | **0285** |
| **D2733** | Stage plan `:1010-1012`: *"a relay at the edge"*; scope-closure §36 `:1751-1755`: *"its `connect-src` gains the relay's `wss:` origin"*. | The console's two cookies are `__Host-…; Path=/` (ADR 0281 `:59-66`): a browser sends them on every request to `control.agenticpostgresql.com` — **a WebSocket handshake to a path on that host included**. No `sql.` record exists on the zone (Session 43's C0 listing, 28 records). | **The operator, 2026-10-21: the relay on its own name, `sql.agenticpostgresql.com`.** Derived once by **`naming.sql_relay_host(control_domain)`** = `"sql." + <the control domain without its first label>` (refused when the remainder has fewer than two labels; `control.agenticpostgresql.com` → `sql.agenticpostgresql.com`), rendered for the control project only as `APG_SQL_RELAY_HOST`; the origin `naming.sql_relay_origin(host)` = `wss://<host>`. **Sheet D0 (Run 1, the agent through the Cloudflare API)**: one A record `sql` → `15.204.231.45`, **`proxied: false`** (the grey-cloud rule: it names the host, ACME HTTP-01 must reach it), read back; nothing else touched. The certificate comes from the edge's existing resolver at R2d (one issuance, never retried in a loop). | The relay never receives a session cookie it would have to ignore; the console's `connect-src` names exactly one more origin. | **0286** |
| **D2734** | Stage plan `:1022-1026`: *"An ADR amending ADR 0246's sentence to 'no product surface runs SQL on the platform's side or holds a credential that opens a project's data; the console may host the customer's own client, which speaks with the customer's own credential through a relay that holds none'"*. | ADR 0246 `:94-99` and `product-contract.md:631-633` hold the old sentence; CLAUDE.md §6 (launch folder, not the repository) restates it; `tests/security/test_dx_surfaces_hardening.py:68,138-150` maps *"A human cannot run SQL through a product surface"* to dev, generate and Studio. | **ADR 0285 amends ADR 0246's sentence** to the brief's words **plus D2732's honest clause**: *"…through a relay that holds none **and records none of what it carries**."* `product-contract.md:631-633` takes the same words (Run 5); `:619` (no agent SQL) unchanged. ADR 0246's own file gets a one-line *"Amended by ADR 0285"* under its status. The DX hardening guard is **unchanged** (dev, generate and Studio still run no SQL). The handoff's CLAUDE.md §6 line is moved at Run 9 (outside the repository). | The sentence was always about who runs a statement and who holds the key; the editor keeps both with the customer. | **0285** |
| **D2735** | Stage plan *Already true* `:1035-1037`: *"…the connection budget; `statement_timeout` per role."* *Must not* `:1041`: *"lift a customer role's grants or timeouts for the editor"*. | **No customer role has a `statement_timeout`** (§0: only `app_runtime` and manifest-named roles; the slot manifest names none, `slot.py:163-179`), **and the customer poolers set no `query_timeout`** (`compose.yaml:798-819`). A customer's `psql` can run a statement for as long as it likes today. | **The premise is false; nothing is lifted and nothing is added to the roles** (a role timeout would change what `psql` gets — a product decision this brief does not take; named in §10). **The editor bounds its own statements**: a **Cancel** control, and an automatic cancel **60 s** after a statement is sent (`STATEMENT_DEADLINE_SECONDS` in `pg.js`), each a CancelRequest through the relay (D2754); the relay closes any session at **30 min** (D2741). The page says so beside the editor (*"A statement still running after 60 seconds is cancelled."*). THR-SQL-DEADLINE (Run 1). | A guarantee the tree does not hold is not cited as one; the editor keeps the bound it can keep. | **0285** |
| **D2736** | Stage plan `:1027-1028`: *"a per-project connection ceiling inside ADR 0070's budget"*; *Measures* `:1046-1047`: *"the project's connection count during an editor session against ADR 0070's budget."* | ADR 0070's budget is per **role**: each customer role's `CONNECTION LIMIT` equals its pooler's server pool (ADR 0269 `:110-115`, 2/2 on standard), and **rig 39e left no headroom for a third claimant on small or standard** (ADR 0269 `:74-78`). PgBouncer admits up to `max_client_conn = 100` clients per door and queues them on its 2 server connections (transaction mode) or holds them to 2 (session mode). | **The relay adds no claimant.** An editor session is one client of the existing pooled or direct door, counted against the role's limit by PostgreSQL and PgBouncer exactly as `psql` is; `max_connections` and the budget do not move. **The relay's ceilings are client-side** (D2741): **32** concurrent sessions in total, **4** per door host, **4** per source address. **The measure (Run 8, E1)**: the editor itself reads `SELECT count(*) FROM pg_stat_activity WHERE usename = current_user` during a session on each door — at most the role's `connection_limit` from `/connections`. | The budget is enforced where it always was; a relay that claimed connections would have to be given ones the profile does not have. | **0286** |
| **D2737** | Stage plan `:1031-1032`: *"a sleeping project answered *asleep* before any connection"*. | A sleeping project's poolers are stopped, so its names refuse **inside the TLS handshake** — identically to a wrong name (ADR 0268 `:68,73`; p4 q4). Nothing on the wire says *asleep*. `GET /v1/projects/{key}` answers `state` (§0). | **The page asks the control API first**: on opening the editor and before every connect it reads `GET /v1/projects/{key}`; `sleeping`, `suspending` or `starting` → *"This project is asleep. Wake it from Settings, then connect."* and **no socket is opened**; `ready` (or `updating`) → connect; anything else (`unknown` included) → *"The project's state could not be read; nothing was opened."* **A door the relay cannot reach closes with `4502`** and the page says *"The database could not be reached."* — never *asleep* (ADR 0195's third outcome). | Only the control plane knows a project sleeps; a relay that guessed would turn an outage into a reassurance. | 0195, **0285** |
| **D2738** | Stage plan *Must not* `:1042`: *"present the editor for a project the Ledger does not offer it on"*. | Only a slot has doors; `GET /v1/projects/{key}/connections` answers `409 not_available` naming `pooled_endpoint` for any other project (`control_routes.py:1026-1049`). | **The editor reads `/connections`**; a `409` is the page's existing *not available* text (the Connect page's), and no control renders. Its two doors come **only from that answer** (`host`, `port`, `user`, `database`) — the page types no host. The view's Ledger rows: `sql_editor`, `pooled_endpoint`, `direct_endpoint`. **Branch doors are not offered in this session** (the grammar admits them, D2740; listing them is a later page — §10). | The answer the CLI already trusts decides where the editor exists. | **0285** |
| **D2739** | Stage plan `:1012-1013`: *"connects only to that project's own public names"*. | The door is Traefik's `postgres` entrypoint (`:8432`, published 5432). The edge answers **`apg-edge-proxy`** on every project's `edge` network (ADR 0167, `host_config.py:291`) — the control project's included. A container reaching `15.204.231.45:5432` (hairpin through Docker's NAT) is **unmeasured**; the host firewall filters only the public interface (`infra/host/docker-user-rules.v4:35-54`). | **The relay connects to `apg-edge-proxy:8432`** on the control project's `edge` network (rendered `APG_SQL_RELAY_UPSTREAM`, from `host_config.EDGE_PROXY_ALIAS` and the entrypoint's port — never typed), sends **SSLRequest**, requires `S`, then TLS with **SNI = the requested public name**, **ALPN `postgresql`**, **`CERT_REQUIRED` + hostname check against the image's system trust store** (`python:3.12-slim` carries `ca-certificates` — rig 44c reads it), TLS ≥ 1.2. **The edge's `sniStrict` routing is the only router**: the relay resolves no DNS and reaches no other address. Rig 44c measures the SSLRequest path, ALPN and the verify against a rig CA (control: a wrong CA refused); **E0 (Run 8) reads it live** from the host. | The relay walks through the same door a stranger does, by the name the certificate proves. | **0286** |
| **D2740** | Stage plan `:1027`: *"routed by name to one project's pooled or direct name and nowhere else"*. | Door names: `pool.<domain>`, `direct.<domain>`, `<branch>.pool.<domain>`, `<branch>.direct.<domain>` (`naming.py:553-568`, `:1112-1126`); slot domains are one label under the zone (`slotN.agenticpostgresql.com`, host.yaml). | **The relay's one path**: `GET /v1/door/<host>` upgraded to a WebSocket; `<host>` must fullmatch **`^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)?(?:pool\|direct)\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.<zone>$`** (the zone escaped), length ≤ 253; the zone is rendered `APG_SQL_RELAY_ZONE` by `naming.sql_relay_zone(control_domain)` (the control domain without its first label). Anything else — an IP literal, a port, uppercase, a query string, another label count, another path — is refused **before any TCP** (`400` before the upgrade). **An agreement test** feeds `endpoint_hosts` and `branch_endpoint_hosts` for slot domains under the zone through the grammar (all match) and `control.<zone>`, `<zone>`, `api.slot3.<zone>` (none match). A name that matches and has no router (`pool.control.<zone>`, `pool.slot99.<zone>`) reaches the edge and is refused there → `4502`. | A pattern derived from the names `naming` makes, refused before a socket, leaves the relay no target the public door does not already answer. | **0286** |
| **D2741** | Stage plan `:1012`: *"a relay … that authenticates nothing"*; `:1028-1029`: *"idle and total time limits"*; THR *"exhaustion of the relay"*. | The door is already public (5432, ADR 0268): anyone can open what the relay can open. Traefik sets the client's address in `X-Real-Ip`/`X-Forwarded-For`; **no `forwardedHeaders` trust is configured** (§0), so whether a client-supplied `X-Forwarded-For` survives is Traefik's behaviour — unmeasured. | **The relay authenticates nothing and checks three things**: (1) **`Origin` equals the console's origin byte for byte** (`APG_SQL_RELAY_ALLOWED_ORIGIN` = `naming.console_origin`), else **`403` before the upgrade**; (2) the grammar (D2740); (3) **the ceilings** — 32 sessions, 4 per door host, 4 per source (`X-Real-Ip`, **only if rig 44a shows Traefik overwrites a client's value**; otherwise the per-source ceiling is dropped and the ADR says so) → close **`4429`**. **Time and size**: idle **300 s** (no frame either way) and total **1,800 s** → `4408`; one message ≤ **1 MiB** (`max_size`) → `1009`; bytes towards the browser ≤ **64 MiB** per session → `4413`; bytes the browser sends before the door is ready ≤ **64 KiB**, else `4413`. **Pings every 20 s** (D2751). Every number one constant in `services/sql-relay/relay.py`, stated in ADR 0286, each proved by a test. | A relay that adds no reach needs no identity; what it must not become is a free pool of sockets or a way to hold one forever. | **0286** |
| **D2742** | Stage plan `:1026`: *"The relay: its own bounded service"*. | No WebSocket code or dependency in any image (§0). Writing RFC 6455 framing here is ~250 lines of parser in front of the internet. The auth image's pattern pins a pure-Python package through `versions.in.yaml` (`segno`, Session 43). | **`websockets` (asyncio server), pinned** as a `registry: pypi` entry `WEBSOCKETS_VERSION` in `versions.in.yaml` → `versions.env` by `bin/lock-versions.sh --update --packages-only` (no image moved; D2690's lesson: the dev lock is NOT relocked), installed in `services/sql-relay/Dockerfile` by `pip install "websockets==${WEBSOCKETS_VERSION}"` + an import self-check. **Rig 44d** reads the newest release ≥ 14 days old, its licence (expected BSD-3-Clause), `requires_dist` (expected none), the wheel's sha256, and measures `origins=` (a foreign Origin answered 403 before the upgrade; control: the listed origin 101), `max_size`, `ping_interval`, and the `process_request` hook. **If it has a dependency or a non-permissive licence: §9's stop.** | A maintained parser with a one-line pin is a smaller risk than our own. | **0286** |
| **D2743** | Stage plan `:1029`: *"no payload logged (the canary)"*; *Must not* `:1040`: *"store, log or forward the customer's credential"*. | Traefik's access log drops `Authorization` and `Cookie` and never sees WebSocket frames; the console server logs method, path, status (`serve.py:112-117`). | **One line per session on stdout, and nothing else**: `apg-sql-relay session=<16 hex> door=<host> outcome=<closed\|refused\|unreachable> code=<n> seconds=<n> up=<bytes> down=<bytes>`; refusals before the upgrade log `refused reason=<origin\|path\|ceiling>` with **no `Origin` value and no path beyond the door host**. No frame, no SQL, no row, no SASL message, no header. **Offline canary** (`test_no_line_holds_the_payload`): a session through the relay with a known password (SCRAM) and a known marker inside a statement; every captured line read; neither appears. **Live canary**: the editor walk sends `SELECT 1 /* apg-s44-<12 hex> */` (the marker in the record, not a secret); the host proof greps the relay container's whole log for it → absent (D2750). | A relay that can read must be shown, live, not to write. | **0286** |
| **D2744** | ADR 0280 `:147-149`: *"That session's ADR amends this constant."* | `CONTENT_SECURITY_POLICY` is a literal (`serve.py:71-83`), asserted equal to a second literal (`test_console_server.py:33-37,106,117`); the console's environment is exactly two names (`test_console_plane.py:122`); `env.json` answers `{"api"}` (`serve.py:150-156`). | **The policy is built once at start from a rendered origin**: `serve.policy(relay_origin)` = ADR 0280's string with `connect-src 'self' <relay_origin>`; `APG_CONSOLE_SQL_RELAY_ORIGIN` (`wss://sql.agenticpostgresql.com`, from `naming.sql_relay_origin`) passed by compose as `${…:?required}`; a value that is not exactly `wss://<host>` (no path, no port, no `*`) **refuses to start**. `env.json` gains `"sql_relay"`. **The tests become stricter, not looser**: `POLICY` becomes the exact string for a fixture origin; a second test proves every other directive is byte-equal to ADR 0280's; a third refuses `ws://`, `wss://*`, a path, an empty value. The site's CSP (`site_build.py:62-74`, `connect-src 'none'`) is untouched. | One origin more, named by the same authority that names the relay. | **0285** |
| **D2745** | ADR 0280 Decision 5 (`:101-106`): *"No script builds SQL, writes `localStorage` or `sessionStorage`, or holds a token."* | The guards in §0. `test_no_script_holds_sql` (`test_console_pages.py:98-103`) scans `public/*.js` for statement shapes; the editor's statements are typed by the person, never held by a script. | **Kept and extended, never loosened** (ADR 0285): `test_no_script_holds_sql` **unchanged** (`pg.js` holds protocol, not statements — the page's placeholder text is not a statement: *"Write a statement"*); `test_no_script_writes_storage` unchanged (now covers `pg.js`); **new `test_only_pg_js_opens_a_websocket`** beside `test_only_api_js_calls_fetch`; `test_console_scram.py:84-85` names `["api", "app", "pg", "scram"]`; `LISTED`/`ROUTES` gain `/console/pg.js`; `test_console_plane.py:122` the environment exactly three names; `test_site.py:165`'s unreachable example `sql_editor` → **`passkeys`** (a row that stays `planned`) — the same assertion, a different fixture, made in the bump run that moves the row. | A guard that held while the page had no editor must hold harder with one. | **0285** |
| **D2746** | Stage plan `:1032-1033`: *"The Ledger's `sql_editor` row out of `not_offered` to `trial` with its claims."* §11: *"The Reality Ledger moved in the run that builds the thing."* | The row is **`planned`**, `target_session: 44` (`reality-ledger.yaml:988-1003`; Session 43's bump moved it). A view naming it fails `test_every_console_page_maps_to_a_reachable_row` while it is `planned`; a `trial` row needs its `target_session` = `CURRENT_SESSION` (`reality_ledger.py:174-189`), which is 43 until the bump. Session 43 landed its pages behind a named exception for the `console` row (Run 4), removed at its bump. The `console` row says *"the console has no data view and runs no SQL"* (`:223`, `:248`); four `planned` agent-plane rows say *"the console has no data view (D2661)"* (`:1180,1197,1214,1231`). | **Run 5 lands the editor view behind a named exception** for `sql_editor` in the guard (one id, a comment naming this row; removed by Run 7). **Run 7 (the bump)**: `sql_editor` → `trial` with `evidence` = `sql_editor_live`, `sql_relay_live`, `sql_relay_host` (ADR 0261), `customer_text` *"Being verified: a SQL editor in the console that connects as your own database role, with your password held only in the page."*, `controls: [/console/]`; the `console` row's two sentences rewritten (*"…runs no SQL on the platform's side; the SQL editor is your own client"*); **every `no data view` sentence re-read** and rewritten only where it became false (the agent rows speak of *agents'* data; Run 7 decides each and lists them). **Run 9**: `sql_editor` → `beta` only if its claims passed. A site page `site/pages/docs/sql-editor.md` (ledger `sql_editor`, `pooled_endpoint`, `direct_endpoint`) lands in Run 7. | The stage plan's row was overtaken by Session 43; the guard decides order, and the exception keeps the order honest. | 0261, **0285** |
| **D2747** | Scope closure §36 inherits 2b (`:1758-1761`): *"Session 44's release prices them (`image_digest`) and deploys them. Check both pins' indexes before any session that rebuilds the image."* | `9fa9042` changed `versions.env:33-34,45-46` — the Postgres image (`pgvector/pgvector:pg18` + pgBackRest + ca-certificates) is a different image. **A changed image recreates the `postgres` container on every project**: a database restart each (Session 42's release: rest down 2.1–4.2 s, auth 7.6–8.7 s). Session 43's release restarted none. | **Priced and taken**: R1 reads `image_digest` among the changes (with `--also` as D2726 needs); every R2 sheet says *"this deploy restarts the database"*; the windows are probed (`s44-window.py`) and recorded. **Run 1 re-reads both indexes** (the comments' own commands, `versions.in.yaml:576-603,616-642`) — if a pin expired again, Run 2 repins by D2731's method before any image is built. `slot3-prod` has no branch live (p1), so nothing else restarts with it. | The release that was owed is this one; a restart named on the sheet is an operation, one discovered is an outage. | — |
| **D2748** | §7 of every Stage 5 plan: the lifecycle claims re-earned at each release. | **D2714's mechanism stands**: the Session 38–42 lifecycle and branch proofs assert their record's `source_commit` equals the control project's (*"a record from another release"*) and pin its `session` to a tuple; at 1.22.0 the Session 43 records fail **16 external claims and two host branch claims**. `slot1-`…`slot7-prod` are consumed. | **The sixth re-earning, in the sitting, on a new `slot8-prod`** — Session 43 Run 10 step 4b's shape whole: **Run 6** widens the record-session checks to accept 44 (each `in (…, 43, 44)`, count-asserted, the anchors pre-flighted) and derives `s44-lifecycle.py`/`s44-branches.py` and the trip scripts from `~/s43/run8` by named substitution; **Run 8**: H1 (`slot8-prod` in BOTH `host.yaml` copies, `s44-hostyaml.py` — **its inserted comment read, D2727**), SL1 (three grey A records and two R2 buckets EEUR by the agent; the B2 bucket + key, the R2 tokens and the six Infisical secrets by the operator), SL1b, SL2, SL3, RC1, the lifecycle (organisation `lifecycle-s44`), K2, the branches on `slot3-prod` AFTER both walks, A1', B1, SL4 after the tag. **Session 45's walk then needs `slot9-prod`** (§10). | A record from another release is refused by design; widening the check to an older commit would weaken a passing proof. | 0280 |
| **D2749** | Scope closure §36: `console` is `beta` on Session 43's evidence. | `tests/external/test_session43_console.py:210-216` asserts the walk record's `(session, mode) == (43, "live")` **and** `source_commit == control["source_commit"]` — at 1.22.0 `console_walk_live` and `console_csrf_live` would fail on Session 43's record. | **The console walk is re-run in the sitting** (W1′, `s44-walk.sh`, derived from `~/s43/run8/s43-walk.sh`; the record's session check widened to `(43, 44)` in Run 6, the commit check unchanged): a new walker `walk-s44-<6 hex>` invited by the probe owner, onboarded with TOTP, **rotating `slot3-prod`'s `customer_app` again from Connect** — the creds file replaced (the old kept as `customer_app.before-s44`) — then removed. **The editor walk runs after it** and reads the new password from the file. | The proof that the console works at the deployed commit is a walk at that commit. | 0280 |
| **D2750** | *Measures* `:1044-1047`: *"The relay's memory and connections under a control load; a query's time through the editor against the same query through `psql`; the project's connection count during an editor session against ADR 0070's budget."* | Nothing measures a relay. | **Four readings, each with its vantage named**: (1) **the relay's memory and pids** at rest and under **rig 44a's load** (32 sessions, each streaming `generate_series` rows; the control: 0 sessions) — `docker stats` peaks on the workstation; on the host the container's `memory.peak` read by the host proof as root (S1); (2) **editor vs `psql`**: the median of 20 `SELECT 1` round trips through the editor (the driver times each `query()` call) and through `psql` from the workstation to the same pooled door (the instrument, `\timing`) — **named as the workstation's**; (3) **the role's connection count** during an editor session on each door (D2736); (4) the walk's link-free path: sign in → first result. Run 9 writes them to `capacity.ENVELOPE`'s Session 44 section. | A number with its vantage point named, for each sentence the brief wrote. | — |
| **D2751** | Stage plan `:1016-1022`: the rig. | `websecure` has `readTimeout 30s, writeTimeout 30s, idleTimeout 60s` (`traefik.yaml:94-100`). What Traefik 3.7 does with these on an **upgraded** connection is unmeasured; the edge has never carried a WebSocket. | **Rig 44a measures it in Traefik's pinned image with the same entrypoint settings**: a WS session idle for 150 s with no pings, one with pings every 20 s, and one streaming continuously for 150 s — which survive. **The relay pings every 20 s regardless.** **If Traefik closes an upgraded connection carrying traffic before 1,800 s, §9's stop**: the cure is an entrypoint change, which recreates the shared edge (both slots' and every project's outage, 24.4 s, Session 35) — the operator's decision, not this plan's. | The relay's total limit is a promise only if the edge keeps the socket that long. | **0286** |
| **D2752** | Stage plan §10 (`:1287-1289`): each session's gate derived by diff from the newest. | Session 43 added one flag, `--console-record-file` (D2677). | **`bin/session-44-check.sh` derived from 43's by diff**; header and usage rewritten whole (D1488); **one flag added**: `--sql-editor-record-file FILE` (external mode only; exported as `APG_SQL_EDITOR_RECORD_FILE`; refused in other modes with the gate's existing usage error). `tests/contract/test_session_forty_four_gate_modes.py` from 43's by the same method. **The external module, the roster entry and the gate land in ONE commit** (D2715) — Run 7's. | The gate grows by exactly the one input the new proofs read. | — |
| **D2753** | Stage plan §11: the `THR-*` rows first. | The hosted list ends at item 21 (`threat-model.md:452`); its preamble moves each item into the table *"in the run that registers the requirement"* (`:198-201`, D2681). | **Run 1 appends hosted items 22–26** (§5 Run 1); **Run 7 moves each into the table** as `THR-SQL-PROXY`, `THR-SQL-SECRET`, `THR-SQL-EXHAUST`, `THR-SQL-READ`, `THR-SQL-DEADLINE`, target session 44, with their registered requirements. | The table holds only rows whose requirement exists. | 0285, 0286 |
| **D2754** | — (the editor's Cancel, D2735) | ADR 0268 `:74`, `:97-100`: a plaintext CancelRequest did not cross the gateway; an **encrypted** one (libpq ≥ 17) cancelled in 3.0 s. PgBouncer issues its own cancel keys (`BackendKeyData`) and forwards a cancel by them. | **A cancel is its own relay session**: the page opens a second WebSocket to the same `/v1/door/<host>` and sends the 16-byte CancelRequest (code 80877102, the pid and key from `BackendKeyData`) as its first message; the relay does what it always does (SSLRequest + TLS, then forwards), so **the cancel arrives encrypted**; the door answers by closing. The cancel session counts against the ceilings and ends at once. **Rig 44b measures it through PgBouncer in transaction and session mode** (`SELECT pg_sleep(30)` → `57014` within 5 s; control: no cancel → the statement completes). | The one cancel the door is known to pass is the one the relay can make. | **0285** |
| **D2755** | Stage plan `:1031`: *"result rows and bytes capped"*. | — | **The page shows at most 1,000 rows and 2 MiB of row text per statement**; past either, it stops rendering, **sends a cancel**, and says *"Showing the first 1,000 rows; the rest were not read."*; the relay's 64 MiB per session (D2741) is the backstop. Cells render as text nodes only (`textContent`, never markup — `test_no_markup_is_built_from_a_value` holds). Multi-statement input: every result is shown in order; the first error ends the batch as PostgreSQL does. **No export, no download, no history kept** (nothing written to storage — the guard). | Bounded by the page that renders and by the relay that carries, so a careless `SELECT *` costs a cancel, not a tab. | **0285** |
| **D2756** | Stage plan `:1030`: *"the password never written to storage"*. | `connectView` shows a generated password once and nulls it (`app.js:403-429`); ADR 0280 Decision 7: held in a closure, never storage or a URL. | **The editor asks for the password** in one `<input type="password" autocomplete="off">` inside a form whose submit is intercepted (`form-action 'none'` holds); the value is read once into the connection's closure and **the input is cleared immediately**; the closure drops it on disconnect, on leaving the view, and on `pagehide`. The page never offers to remember it. The Connect page gains a link *"Open the SQL editor"* (its rotation is how a person who lost the password gets a new one). | The page that holds the most valuable secret holds it for the least time. | **0285** |
| **D2757** | Stage plan *Measures* and §7: the editor proved live. | Sleeping a project live costs ~70 s down for its names (Session 43: 69.4 / 72.2 s) and `slot3-prod` is the kept customer project; `slot8-prod` sleeps inside the lifecycle instrument, which drives the CLI, not a browser. | **The *asleep* answer is proved offline** (`test_console_sql.py::test_an_asleep_project_opens_no_socket`, the page in Node with a fake `api.js`, every state in `control_states` walked; **the control**: `ready` opens one) **and the `4502` path live** (E1: a door name that matches the grammar and has no router — `pool.slot99.<zone>` — closes `4502`; the same handshake refusal a sleeping door gives, ADR 0268 `:73`). Sleeping `slot3-prod` for the editor is not done. | A live proof of a sentence the control API already proves live (`idle_sleep_live`) is not worth a customer project's outage. | 0195 |
| **D2758** | — | The walk's console identity: Session 43 invited a NEW walker per walk; the probe owner (`~/s37/probe.json`, its password and TOTP seed in `~/s37/probe-password`, `probe-otpauth`) owns `probe-s37`, which holds `slot3-prod`. | **The editor walk (E1) signs in as the probe owner** (the driver computes the code from the seed with stdlib `hmac`; the seed, the console password and the database passwords live in variables only and are `Secret`-wrapped, D2420; `self_check` refuses a record holding any of them, the console walk's rule) — **no new account, no rotation**. It reads `customer_app` from `~/s39/run11/creds/slot3-prod/` AFTER W1′ (D2749) and `customer_admin` from the same directory. | The editor needs a signed-in member, not a new one; a rotation belongs to the walk that proves rotation. | — |

**Rows added by the runs** (from **D2759**, in execution order; **next free D2808**):

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2759** | Run 1 step 1: *"Session 43's 28 plus `slot7-prod`'s three greys"* (31). | The zone held **33** records before D0 (34 after): the two branch wildcards `*.pool.slot3` and `*.direct.slot3` (Session 40's) were not in the count. None named `sql`; only the two Pages CNAMEs proxied. | Recorded; the stop was about a `sql` record, and there was none. Sheet D0 proceeded. | A count that was wrong by two in the reassuring direction is still a count to correct, not a reason to stop. | 0286 |
| **D2760** | §4: *"a name nothing routes yet answers the edge's 404"*. | The edge answers `sql.agenticpostgresql.com` on 443 with a **TLS alert `unrecognized_name` (112)** (curl 35 from Windows and WSL): the default TLS option's `sniStrict` gives no certificate for a name with no router, so no HTTP is spoken at all. | Recorded. Nothing reads the name before R2d; the certificate is issued over HTTP-01 on port 80, which `sniStrict` does not touch. E0 reads the name only after R2d. | What the edge answers before a router exists is a fact of the TLS option, read rather than predicted. | 0286 |
| **D2761** | D2731 (`versions.in.yaml` comment): *"the index offered 2.59.2 and 2.59.3 -- 2.59.1 was gone"*. | 2026-10-21 18:14Z: the pgdg index lists **2.59.3, 2.59.2 and 2.59.1**; bookworm-security lists `ca-certificates 20250419~deb12u2`. Both pins present. | **Both pins stand; nothing is repinned.** The comment's account of 2.59.1 is left as Session 43 recorded it (what the cache-cold build met); this row records the later reading. | The pins are present, which is all D2747 asked; the index's churn is upstream's. | — |
| **D2762** | D2741: *"`Origin` equals the console's origin … else `403` before the upgrade; (2) the grammar"*; D2743: *"one line per session … and nothing else"*. | Rig 44d: `websockets` 17.2 runs **`process_request` before its own `origins` check** (a bad path with a foreign `Origin` → `400`), and **logs a handler's traceback on its own logger** (`websockets.server`, *"connection handler failed"*). | **The relay checks `Origin` itself, first, inside `process_request`**, then the path, then the ceilings (it does not rely on `origins=`); **the library's loggers get a handler that writes nothing** and the relay catches every session exception itself. The offline canary reads every line the process writes, the library's included. | Left to the library, the order of refusals and the log's content would be the library's. | 0286 |
| **D2763** | D2751: *"If Traefik closes an upgraded connection carrying traffic before 1,800 s, §9's stop"*. | Rig 44a: through Traefik 3.7.10 with `websecure`'s 30/30/60 s, **every 150 s session survived — idle with no pings included**: none of the entrypoint's timeouts applies to an upgraded connection. | **No stop.** The relay's own idle 300 s is the only idle bound; the 20 s pings are kept for what lies between the browser and the edge, not for Traefik. | The measurement answered the stop's question in the favourable direction, beyond the margin asked. | 0286 |
| **D2764** | D2741: *"4 per source (`X-Real-Ip`, only if rig 44a shows Traefik overwrites a client's value)"*. | Rig 44a: a client sending `X-Forwarded-For: 203.0.113.9` and `X-Real-Ip: 198.51.100.7` — the relay saw **both replaced by the true peer** (the control, no client headers, the same). | **The per-source ceiling stays**, keyed on `X-Real-Ip`. | The edge overwrites the header, so a client cannot choose its own bucket. | 0286 |
| **D2765** | D2732 / rig 44b (1): *"the control: a wrong password → `ErrorResponse` `28P01`"*. | Through the door's shape a wrong password reads **`08P01` *"SASL authentication failed"***: PgBouncer authenticates the client itself (its userlist holds the verifier), so PostgreSQL never sees the attempt. | **Every proof and the page read `08P01`** for a wrong password through a door (`test_console_pg.py`, E1); the page's text is *"The database refused the password."* for `08P01` and `28P01` alike. | The answer a customer gets is PgBouncer's; a proof expecting PostgreSQL's would fail on first execution. | 0285 |
| **D2766** | Rig 44b (6): *"the 1,000-row cap → the cap's cancel ends it and the socket stays usable"*; D2755. | A fast statement **finishes before the cap's cancel lands** (200,000 rows, 3.29 MB in 0.27 s, rows past the cap read and dropped); a statement **still producing rows** is ended by the cancel with **`57014`** after ~1,380 rows in 1.8 s. Either way the next statement ran. | **The next statement is sent only after a cancel's own session has closed** (a late cancel cannot reach it); **the cap's own `57014` is shown as the cap's sentence, never as an error**; `test_the_row_cap_cancels` uses a statement still producing rows (`pg_sleep` per row), with the fast statement as its second case. | A cap that sends a cancel must own what the cancel does, including when it arrives too late to matter. | 0285 |
| **D2767** | D2732: SCRAM-SHA-256 with the server signature verified. | Nothing in the plan bounds the server-first message's iteration count: anything between the page and the door that rewrote it could lower `i` and make an offline guess against a captured exchange cheaper. | **The client refuses a server-first whose iteration count is below 4,096 (PostgreSQL's default) or whose nonce does not extend its own.** Threat item 25 names it. | The relay can read and could rewrite; the client can refuse what would weaken its own proof. | 0285 |
| **D2768** | D2737: *"anything else (`unknown` included) → 'The project's state could not be read; nothing was opened.'"* | Rig 44e: `creating`, `deleting` and `deleted` would be told the state *could not be read* — but it was read. | **Named**: *"The project is <state>; nothing was opened."* for `creating`, `deleting`, `deleted`; *could not be read* only for `unknown`, an unexpected value or a failed read. | ADR 0195: the third outcome is *I could not determine it*, not *I determined something I would rather not say*. | 0285 |
| **D2769** | Run 1 step 5: *"the close codes `4400 4403 4408 4413 4429 4502`"*. | Rig 44d: an `Origin` refusal is an HTTP `403` **before** the upgrade (and D2762 puts it first), so no WebSocket exists to carry a close code for it. | **The close codes are `4400` (a text frame), `4408`, `4413`, `4429`, `4502`; `4403` is dropped.** | A code that can never be sent is a promise no test can hold. | 0286 |
| **D2770** | Rig 44e: *"read whether the editor's logic can be a DOM-free module (`sql.js`) … Recorded: the module boundary Run 5 uses."* D2745 lists `pg` as the only new script. | Rig 44e: a module that imports nothing and takes `call` and `connect` as arguments runs in Node with stubs; a module touching `document` at import fails there. | **`services/console/public/sql.js` is the console's fifth script** (Run 5): `ROUTES`/`LISTED` gain `/console/sql.js` as well as `/console/pg.js`, the scripts' name list is `["api", "app", "pg", "scram", "sql"]`, and `test_no_script_holds_sql`, `test_no_script_writes_storage` and `test_only_pg_js_opens_a_websocket` cover it. | The plan asked the rig for the boundary; the boundary is a file, and every guard over the console's files must name it. | 0285 |
| **D2771** | D2742 / rig 44d: *"the newest release ≥ 14 days old"* (17.2), *"the dev lock is NOT relocked"*; Run 2 step 4: the relay tested **in-process**. | The dev lock holds `websockets==17.1` (a transitive of `fastmcp-slim`) and its cutoff is `2026-09-03T15:16:21Z`; 17.2 was published 2026-10-03, after it. In-process tests would serve the relay with 17.1 while the image ran 17.2 — two versions, one proved. | **The pin is 17.1** (2026-08-26, 56 days; BSD-3-Clause; no `requires_dist`; wheel `0c863507…`, sdist `acfea4c2…`, both already in the dev lock's entry): rig 44d re-run on 17.1 read every answer identical (`~/s44/rigs/44d/rig-17.1.txt`). `test_websockets_is_locked` holds all four places, `test_segno_is_locked`'s shape. ADR 0286 names it. | One version proved is the version shipped; moving the dev lock's cutoff to reach 17.2 would move every floating dev dependency (D2690). | 0286 |
| **D2772** | Run 2 step 4: *"the CA file passed by a test-only argument that the image never reads — a guard proves the image's entrypoint passes none"*. | `ssl.create_default_context()` reads OpenSSL's `SSL_CERT_FILE` (measured in the tests: a relay built with it set to the trusted CA reaches the door, with the stranger CA closes `4502`). | **The relay has no CA parameter at all**; the tests set `SSL_CERT_FILE` (in-process by `monkeypatch`, and in the canary's subprocess environment), the way any trust store is moved. **`test_the_relay_reads_no_secret_and_no_file` is the guard**: no `cafile`/`capath`/`cadata`, no `load_verify_locations`, no `open`, imports from a closed set, the four `APG_SQL_RELAY_*` names and no other, and the Dockerfile's `ENTRYPOINT ["python", "-u", "/app/relay.py"]` exactly. | A parameter that only tests use is still a parameter production code could reach; a guard over its absence is stricter than a guard over its non-use. | 0286 |
| **D2773** | Run 2 step 2: *"the path grammar (D2740) and the ceilings (D2741) → an HTTP refusal before the upgrade; `origins=[ALLOWED_ORIGIN]` (rig 44d)"*. | ADR 0286 decision 3 (from D2741 and D2762): `Origin` checked by the relay itself, FIRST, in `process_request`; the ceilings close `4429` after the upgrade so the page can say why. | **The relay passes no `origins=`** and checks `Origin` itself, then the path; **the ceilings close `4429`** after the upgrade, as D2741 and the ADR say; `GET /__apg/healthz` is answered before the `Origin` check (the container's own healthcheck sends none). Battery mutation 1 (the `Origin` check removed) was KILLED **because** no second check stands behind it. | A belt behind the check would make the check's own test unable to fail; and a browser shows an HTTP refusal of a handshake only as `1006`, never a reason. | 0286 |
| **D2774** | Run 3 step 2: *"limits … **pids 64, cpus 0.5, memory 128 MiB** — Run 1's rig 44a peak under 32 sessions × 2 at least; if the peak exceeds 64 MiB, the limit is twice the peak"*. | Rig 44a's 19.5 MiB was the rig's echo server, with no TLS leg to a door. **The real relay image**, read-only as compose runs it, under 32 sessions each streaming 10 KiB/s through TLS on both sides (`~/s44/run3/measure.txt`): **memory.peak 40.49 MiB, pids.peak 21** (20.1 MiB / 3 at rest; 19.4 MB delivered, no error). ADR 0244's rule for every bounded service (`config.SERVICE_MEMORY_LIMITS_MB`'s docstring): the larger of 64 and 4 × peak, rounded up to 32. | **pids 64 (the floor), cpus 0.5, memory 192 MiB** (4 × 40.49 = 162 → 192), the project's rule over the plan's ×2; recorded in `config.py` beside the console's. | One rule for every ceiling; the plan's ×2 would have been the only service bounded more tightly than the rule allows. | 0286 |
| **D2775** | D2733: *"`naming.sql_relay_host(control_domain)` … refused when the remainder has fewer than two labels"*. | The committed control example's domain was `fixture-control-dev.test`: its zone would be the bare TLD `test`, and the render refused it. `test_control_routes_rendered` made `project.second.example.yaml` a control project the same way (`fixture-alpine-dev.test`). | **The refusal stands; the control example takes the deployment's shape**, `control.fixture-dev.test` (zone `fixture-dev.test`, relay `sql.fixture-dev.test`), and the routes test's helper prefixes `control.` when it turns a manifest into a control project. The two literals that named the old domain (`control_cluster.py`, `test_control_set.py`) moved with it; **every module that renders the control example ran** (D979). | A zone of one label would let the grammar admit door names under a whole TLD; a fixture is moved to the production shape rather than the guard to the fixture's. | 0286 |
| **D2776** | Run 2's `**Done.**`: *"Targeted, once … 443 passed"*. | **CI on `8c1d1a8` FAILED** (`contract` run 39659742863: *Session 2 offline contract* and *Session 1 gate*, 1 failed of 8,282): `test_a_large_message_is_refused` sent its 1 MiB control frame before the fake door's TLS was ready, met the 64 KiB pending cap (`4413`, the relay as designed) — a race the workstation never lost. And Run 3's shard found the canary's refused statement flaky: the random marker unquoted parses as arithmetic (`42703`) or not at all (`42601`). | **Test-only repair at `ef48bec`**: the large-message test establishes the door with a round trip first; the canary quotes the marker (`42703`, always). No product change. Any test that sends more than 64 KiB must first see the door answer. | A green workstation run is one sample of a race; CI is the second machine. | — |
| **D2777** | Run 4 step 2: the live tests run `pg.js` in Node against the relay of Run 2. | Measured (`~/s44/run4/origin.txt`): **Node 22's global `WebSocket` sends no `Origin`**, so the relay refuses it `403`; undici's `new WebSocket(url, {headers})` sends the one given. And a refused handshake fires `error` and **never `close`** (readyState stays 0). | **The test driver wraps the global `WebSocket`** with the console's `Origin` before calling `pg.js`; `pg.js` has no seam for it. `pg.js`'s `opened()` treats an `error` before `open` as the refusal (`closeCode` 1006) and keeps a 15 s timer, so no runtime can leave a connect hanging. | A browser always sends `Origin`; the stand-in must, and the client must not depend on a `close` that some runtimes never fire. | 0285 |
| **D2778** | Run 4 step 2: *"the in-process relay from Run 2"* with the Node container. | The workstation's Docker is **Docker Desktop** (29.5.2): `--network host` is its VM's namespace, not WSL's — the first live run never reached the relay (no relay line at all). | **The live half runs Node on the bridge network with `--add-host host.docker.internal:host-gateway`** and the in-process relay bound to `0.0.0.0` (a test's listener, `noqa: S104`), which also holds on CI's Docker Engine. | One fixture that reaches the relay the same way on both machines. | — |
| **D2779** | Run 4 step 2: *"the SCRAM proof against Python's (fixed nonce and salt passed by a test-only hook the page never calls — a guard that `app.js` never passes it)"*. | The proof is a function of the password, the client-first message and the server-first message alone. | **No hook**: `pg.js` exports the pure `clientFinal(password, clientFirstBare, serverFirst)`, which `authenticate` calls and the test compares with Python for fixed exchanges; the fake servers of the pure half are a stand-in global `WebSocket`. `connect` takes the plan's five options and one more, `deadlineSeconds` (default 60), which the live test sets to 2 and **Run 5's guard holds `app.js` never passes**. | A seam the page could pass is a seam; a pure function has none, and its test is stricter (two exchanges, three refusals). | 0285 |
| **D2780** | Run 4 read-first: *"`pg.js` imports from it rather than repeating them"*. | `scram.js` exported only `ITERATIONS`, `SALT_BYTES`, `PASSWORD_BYTES`, `newPassword`, `verifier`; its `base64` and `hmac` were private and PBKDF2 inline. | **`scram.js` exports `base64`, `hmac` and a new `scramKeys(password, salt, iterations)`**, and `verifier` is built from `scramKeys`; `test_console_scram`'s verifier-equals-the-CLI's proof is unchanged and passes. | One implementation of RFC 5802's keys in the console. | 0285 |
| **D2781** | Run 4 step 2: *"PostgreSQL 18.4 + PgBouncer (both pool modes) + the in-process relay"*. | In production the edge (Traefik) terminates the door's TLS and PgBouncer speaks plaintext behind it; the relay needs a TLS peer that answers SSLRequest. | **In the test PgBouncer terminates its clients' TLS** (`client_tls_sslmode = require`, a certificate for both door names from a CA made in `tmp_path`); the relay verifies it as it verifies the edge. Traefik's own part was measured in rig 44b and is read live by E0/E1. | The client's and the relay's behaviour is what this test holds; the edge's is rig 44b's and the trip's. | 0286 |
| **D2782** | CLAUDE.md §1 (D386): *"`FAILED` is a kill, `ERROR` is a broken fixture that never reached the assertion."* | Battery round 1: *the cancel sent on the same socket* came out **ERROR** — the one live driver threw at a later `open()` (`53300` *too many connections for role "editor"*: the corrupted cancel left the server connection busy), so the module-scoped fixture failed before any assertion. | **Every live measurement records its own failure as data** (`step(name, f)`), so a broken step fails its own test's assertion and the fixture still delivers; round 2 re-ran all five mutations. | A mutation that breaks the fixture proves only that something broke. | — |
| **D2783** | Run 5 step 1: *"`policy(relay_origin)`, read once at start … (refuse to start unless `wss://<host>` alone)"*. | `serve.py` is imported by its own proofs and by Session 43's external module (`_console_policy`), which loaded it with no environment and compared the live headers with `SECURITY_HEADERS` — at 1.22.0 that comparison would have read a policy without the relay. | **`serve.py` exposes `policy(relay_origin)` and `security_headers(relay_origin)`**; at import an origin that is not `wss://<host>` leaves the headers unbuilt and `REFUSED` set, and **`main` exits 2 before it listens** (the image's own path, proved by subprocess for eleven bad origins). **Session 43's external proof now passes the origin `naming` derives from the console's host** (`_console_policy(console_origin)`), so it compares the live answer with ADR 0285's policy, read here as exactly `… connect-src 'self' wss://sql.agenticpostgresql.com …`. | The module stays importable for the proofs that read it; the server never serves without the policy. | 0285 |
| **D2784** | Run 5 step 2: the view reads the relay's origin. | `api.js` is the ONLY file that calls `fetch` (`test_only_api_js_calls_fetch`) and read `env.json` for the API path alone. | **`api.js` keeps `env.json`'s whole answer and exports `relayOrigin()`**; the editor asks it, so `api.js` stays the one `fetch` caller and no page types the origin. | One reader of the server's environment. | 0285 |
| **D2785** | Run 5 step 3: *"**The Ledger guard's exception** for `sql_editor` (one id …)"*. | Two guards read `pages.json`'s rows: `test_reality_ledger.py::test_every_console_page_maps_to_a_reachable_row` and `test_console_pages.py::test_no_page_names_an_unreachable_row`. | **The same one-id exception in both**, each allowing `sql_editor` only while it is `planned` with `target_session` 44 — a row that moved anywhere else fails both. Run 7 removes both. (ADR 0246's status line, Run 5 step 4's second item, was amended in Run 1.) | A guard the plan did not name would have refused the view. | 0285 |
| **D2786** | Run 6 step 3: *"the marker from the record via an existing host gate or a new one — read the roster first; a new host gate is a row"*. | The host mode takes record files (`--branch-record-file`), but the walk's record is written on the workstation after the deploy, and D2752 gives the gate exactly one new flag, external-only. | **No new host gate.** `test_the_relay_logged_no_payload` reads the relay container's WHOLE log as root and holds: every line fullmatches ADR 0286's session or refusal grammar; no line holds `apg-s44-` (ANY walk's marker), `SELECT`, `SCRAM`, `n,,n=`, `c=biws`, `pg_sleep` or a traceback; and a closed session to the live slot's pooled door is there (the control that this is the log the walk wrote to). | Stricter than grepping one known marker, and it needs nothing carried to the host. | 0286 |
| **D2787** | Run 6: *"Commit (the driver, the host module, the widening)"*; step 5 parks only the external module (D2715). | `test_deployment_suite_shape::test_every_deployment_proof_is_a_node_id_of_some_requirement` FAILED with the host module in the tree: its four proofs are no requirement's node ids until Run 7's registry (D2721's lesson, Session 43). | **The host module is PARKED too** (`~/s44/run6/park/test_session44_sql_relay_host.py`, beside the external module), and lands in Run 7 with the registry, the gate and the roster entry. Its collection and `--setup-plan` with every variable set ran here. | A module the suite-shape guard refuses would turn `main` red for a run. | — |
| **D2788** | D2750 (2): *"through `psql` from the workstation to the same pooled door"*. | The pinned PostgreSQL image carries **no trust store** (D590: `ca-certificates` is not in the base), so `sslrootcert=system` failed: *"certificate verify failed"*. | **The timing mounts the workstation's CA bundle read-only** (`-v /etc/ssl/certs/ca-certificates.crt:/ca.pem:ro`, `sslrootcert=/ca.pem`), the password passed by environment NAME (`-e PGPASSWORD`), never argv. Its shape read once, read-only, against the kept slot3 door at 1.21.0: 20 timings, **median 168.7 ms** (167.2–175.6) — a pre-release reading, named the workstation's. | The image the product builds adds the bundle; the stock one the instrument borrows does not. | — |
| **D2789** | Run 6 step 1: *"A `--rehearse` mode answering from fixtures (the console walk's)"*. | The console walk's fixtures answer `/api/v1` only; the editor also opens a WebSocket to the relay. | **The rehearsal answers the relay too**, with Playwright's `route_web_socket` and a fake PostgreSQL backend in the driver: a real SCRAM exchange against the creds files, canned answers, the cancel by its own socket — so the editor's DOM, `pg.js` in Chromium and the driver ran with no host. It found two driver defects before any trip: `get_by_role("button", name="Connect")` also matched **Disconnect** (`exact=True` now), and `--leak` could not trip the self-check until the record held page text (the overview's headings, the console walk's rule). | A rehearsal that skipped the socket would have skipped the code under test. | 0285 |
| **D2790** | Run 6 step 2: the trip scripts *"derived from `~/s43/run8/` by named substitution and read whole after"*. | The name-based leftover check passed scripts still holding a bare `43`: **`write-session-evidence.py --session 43`** in `s44-external.sh` (the merge would have written Session 43's evidence) and `GATE_43_*` exit names; and the first derivation rewrote the Python children's lineage line into a false one. | **Named steps added for both** (`--session 43`, `GATE_43_`), plus the path-part, module-name, display-name and stage spellings; the parents' docstrings keep their lineage (only usage lines move); a second grep for bare `43` ran after; **every hand edit lives in `s44-post-derive.py`**, re-applied after any re-derivation. The diff of each child against its parent was read (`derive-diffs.txt`). | A check that reads names cannot see a number; the reading of the diff can. | — |
| **D2791** | Run 7 step 1 and §2: 1.22.0 a minor; the price *"read rather than chosen"* (D704). | D1624's rig (a worktree at the deployed `012ac06` against a `tar` copy of this tree, both rendering the installed `project.example.yaml`): `bump minor`, **`requires patch`**, verdict `ok`, `changes [image_digest]`, `reasons []`, `operator_digests_moved []`; two leaves differ (`versions_lock_sha256`, `template_version`). No pair of rendered documents can show a new service under the control project's profile or a console policy, so the reading prices the lock alone. | **`1.22.0` kept, proposed above the reading's floor**: a new public surface (the relay's name, the editor) is a feature, and a minor covers a patch. Written into the release paragraph in ADR 0162's form and into the upgrade table's row. **The trip's `upgrade plan` on every project confirms it; a `major` there is a stop condition.** | The reading prices what a document shows; what an operator meets (a new container, a new certificate) is said beside it. | — |
| **D2792** | Run 7 step 4: `site/pages/docs/sql-editor.md` (what it is, the two doors, the password stays in the page, the relay records none of it); the first draft named the relay's host. | `test_site.py::test_the_site_names_no_host_address` (Run 7's targeted run: 1,389 passed, **1 failed**) admits only the `www.` and `control.` names on a site page — the guard the site has had since Session 43. | **The page names no host**: it says the editor connects through the relay on its own name, which the console reads from `env.json`; the guard is not widened. The gates passed it on `c947180`. | A page that names a host is one more place an address must be kept true; the console already holds it. | 0283 |
| **D2793** | Run 4: the live half of `test_console_pg.py` runs the relay in-process and Node in a container on the bridge (D2778). | Session-01 gate shard 4 at `df5ff04`: **pass, fail, fail — even alone**. On Docker Desktop a port newly bound in WSL answers at `host.docker.internal` only once WSL's localhost forwarding has registered it; the Node container sometimes connected first and every session was refused at the handshake, no relay line written. CI's Docker Engine never lost it. | **Test-only repair at `6f90455`**: the `door` fixture retries a TCP connect to each relay port from a container on the bridge (up to 60 s) before the driver runs (`REACH`, `_reachable`). Four runs green; shards 4–6 re-run on it, passed. No product change. | A workstation race is not a product defect, and a test that loses it reads like one. | — |
| **D2794** | Run 7 step 1: Session 44's paragraph *"the D690 shape of `:1271-1334`"*; Run 7's targeted list. | Session-01 gate shard 9 at `6f90455`: **`test_the_constants_comment_states_the_class_it_proposes` FAILED** — the paragraph said *"`1.22.0` is proposed above that floor"* but never *"ADR 0162 prices it a MINOR"*, and its schema sentence sat in the paragraph before; the proof reads the LAST paragraph only. `test_release_contract` was not in Run 7's targeted list, so the commit carried it (`df5ff04` would have gone red in CI). | **Repaired at `c947180`** (comment only): the last paragraph prices the class in that form and names the five schemas that did not move; `test_release_contract` + `test_gate_contract` (the two readers of the comment) 69 passed; shards 8 and 9 re-run at `c947180`, the first attempts kept (`shard8-attempt1-6f90455.txt`, `shard9-attempt1-df5ff04.txt`). `df5ff04`, `6f90455` and `c947180` pushed together (CI on the head, green). | **A bump's targeted list includes `test_release_contract`** — the class sentence has a reader. | 0162 |
| **D2795** | Run 8 step 3: E0 *"sign-in, the editor, one `SELECT 1` on each door"* at the deployed commit. | E0 at `4b6c024` **EXIT 4**: sign-in and the editor ok, the pooled door FAILED in 0.4 s with no socket — `slot3-prod` read state **`unknown`** to the probe owner, and `sql.js` opens a door only in `{ready, updating}`. The state is computed from the operation history (`control_states.py`), and a `branch.*`, `restore.create` or `credential.rotate` operation (Session 40's branches, W1's rotation) had no decision, so the history read `unknown` from then on. The Connect page ignores state, so Session 43 never saw it. | **ADR 0287** at `224b660`: `ELSEWHERE` — those five types leave the parent's state unchanged, whatever their status; `test_every_operation_type_is_decided_or_elsewhere` guards the class against `operations.OPERATION_TYPES`; targeted 342 passed, battery 3/3. The operator chose *fix, redeploy four* (no V1 re-run): R3a–d at `224b660` with no database restart; RC1/A1/RA/K1 again (`kit-2026-10-22-s44b`); X0, W0′, E0 green; `slot3-prod` read `ready` after W1′'s rotation and after the branches. | A state machine over a growing operation vocabulary guards the vocabulary, not the types it happened to list. | 0287 |
| **D2796** | Run 8 step 5: the lifecycle from WSL (`life-start.sh`, the Bash tool's `run_in_background`, as CLAUDE.md §1 prescribed). | **Attempt 1 was KILLED at 17:12:37Z by the workstation's memory reaper** (the harness kills background tasks when the laptop is low on memory), exactly at the K2 pause — after create, sleep, wake, both resizes, the export, its expiry, the idle sleep (1,189.2 s), usage and notifications had all been recorded. Attempt 2 (`--resume --resume-at-export`) stopped at once, exit 4: the export was refused LOCALLY because attempt 1's `export.dump` existed. | **Detached launch measured and adopted**: PowerShell `Start-Process wsl.exe -ArgumentList "-e bash /abs/x.sh" -WindowStyle Hidden` runs to the end with no harness parent (a `bash -lc` argument list is joined and mangled — `-e` and an absolute path; PATH set inside the script). Every long instrument after it (attempts 3–4, the branches, the delete, the external half) ran this way and finished. Attempts kept in `~/s44/run8/life-attempt1/`, `attempt2-*`, `life-attempt3/`. | A long instrument on this laptop runs detached from the harness, never as its background task. CLAUDE.md §1 updated. | — |
| **D2797** | Run 8 step 5: the idle sleep requested by the reconciler within the window. | **Attempt 3** (17:2xZ, resumed at the export): export again (40,286 B, `pg_restore` 0), expiry ok, the idle setting at 17:34:42 — **no idle sleep requested within 1,620 s**, so it STOPPED at exit 4. `usage show` read samples (latest 18:06:34, unread 0) and no operation began in the window. The decision is SQL (`app.control_request_idle_sleep`, `0008-control-plans-usage.sql:572`: a window of samples awake, read, `requests_counter` unmoved, no customer activity). **NOT DIAGNOSED.** | The operator chose to finish from **attempt 1's record** (its idle sleep requested at 1,189.2 s) with a new `--resume-at-k2` (`k2-mode.py`, count-asserted; the parent kept as `s44-lifecycle.py.before-k2-mode`). Attempt 4 (detached): K2, delete, the second create refused `no_slot`, exit 0 at 18:13:56Z. The samples persist: **Run 9 reads `app.control_usage_samples` for `slot8-prod` after 17:15Z as root**. | A resumed instrument inherits the state its first attempt left in the product — here, a counter the second window may have seen moving. | — |
| **D2798** | Run 8 step 6: the merge, *"Exit 5 for `documented_path` only"*. | **`notifications_live` and `notifications_retrial_live` FAILED** (`test_session41_reearning` / `test_session42_reearning` `::test_every_finished_operation_was_notified[_by_its_outcome]`): the product listed **4** × *"project.export on slot8-prod succeeded"*, while the record expects **2**. The record is attempt 1's (D2797). Attempt 3 ran two MORE real exports (`6a10739b`, `324bfa0d`; `life-attempt3/lifecycle.json` lists all four). Each finished operation was notified exactly once — the product is correct, the record is short. | **The operator chose to tag with it recorded** (D2728's precedent). Not repaired: the record cannot be completed honestly after the fact. Re-earned at the next lifecycle trip with a single-attempt record. | Finishing from an earlier attempt's record leaves the product holding operations the record never saw; a proof that counts the product's history against the record will see them. | — |
| **D2799** (cause corrected by D2807) | Run 4/5's external module `test_session44_sql_editor.py`; §7 `sql_relay_live`. | **Its three refusal proofs FAILED on their first live run** — `TypeError: unhashable type: 'dict'` at `_pooled` (`:203`): `urlsplit(control["routes"]["control"])` assumes a string, but the deployed document's `routes.control` is `{"url": …}` (the launcher `s44-external.sh` itself reads both shapes). The offline fixture shared the proof's belief (D673's class), so nothing offline could see it. The same three refusals were measured live by E1 (foreign Origin 403, outside the grammar 400, unrouted 4502). | **The operator chose to tag with it recorded.** Repaired at Run 9 (`_pooled` reads the route as the deployed document holds it, the fixture made the real shape); re-earned at the next host trip. | A never-executed proof fails on first execution (§7 question 2 — the sixteenth); its fixture must be copied from a real document, never written from the proof's belief. | — |
| **D2800** | Run 8 steps 3–6: E1 (step 4) before B1 (step 5), the sweep after; `sql_relay_host`'s `test_the_relay_logged_no_payload` reads *"a closed session to pool.slot3"* in the relay's log. | **S1** (19:33–20:57Z) failed that proof's control: **B1's reboot RECREATED the relay** (the project unit's `ExecStopPost` is `project down` = compose down, `systemd/agentic-postgres-project@.service:42`), so its log began empty at 19:29, after E1 (15:31). The proof reads only the current container's log (D2786). V1 had failed the same assertion for the converse reason (no walk yet). The forbidden-word and stray-line assertions passed on every log. | **E0 re-run after the reboot** (every step ok, sessions closed through the relay to both doors), then **a second sweep, S1b** (20:59–22:20Z): `sql_relay_host` passed. S1 is kept in `/home/op/s44-sweep1/` (145 claims, 142 passed, 3 failed). | A proof that reads a container's log must follow the last recreation of that container — the plan's order put the walk before the reboot. | — |
| **D2801** | Session 32's `workflow_revocation` (`test_a_revoked_agents_run_stops_at_the_boundary_with_no_call`): the run ends `stopped`. | In **S1** the documented race was LOST: the worker claimed step 1 before the revocation landed, the plane refused the call (`unclassified_refusal`), and the run ended **`failed`**. The docstring promises `stopped` at a later boundary in that branch, and it did not hold. It passed in V1 and in S1b. | Recorded; S1b's pass is the evidence. The proof is order-dependent — an open item for the Session 32 module (a later boundary, or both outcomes read by their cause). | A proof that depends on a race needs both arms decided, or it is a coin. | — |
| **D2802** | Run 8 step 4: E1, the editor walk as the probe owner. | **E1 attempt 1 EXIT 4 at sign-in** (15:29:36Z, 30 s timeout): the executor's own state check had just logged the probe owner in with the same TOTP step, and the driver's `fresh_code()` takes the current step, so the server refused it as a replay. | Kept (`~/s44/sql-attempt1-totp-replay`, `s44-sql-attempt1.txt`, D2724's rule); re-run 45 s later, EXIT 0. Not a product defect — the replay refusal is the product working. | Never log the probe owner in near a walk; a TOTP step is single-use. | — |
| **D2803** | Sheet K2: installed at the lifecycle's pause. | The operator ran K2's `install` at 16:00:54Z — **early**, by mistake, during the create. | Harmless by construction: the instrument takes only a copy newer than the host's clock at its pause (`s44-lifecycle.py:1189`) and reads none before step 7. K2 was run again at the pause (attempt 4). | A sheet step a human can run early must be inert until its instrument asks for it — this one was. | — |
| **D2804** | Run 6: the trip scripts *"derived by named substitution"*; Run 8 step 6: the merge *"with the CI artifact's offline half for the deployed SHA"*. | Text the derivation carried: the walker prefix `walk-s43-` is a constant in `tests/external/browser/console_walk.py:236` (W0′/W1′'s walkers were named `walk-s43-…`); `s44-dns.sh` and `s44-free.sh` print `S42-DNS:` / `S42-FREE:`; `s44-hostyaml.py`'s inserted comment said *fourth/D2561* (hand-fixed before H1, D2727's check); `s44-external.sh`'s merge echo says *"322 claims, 149 offline"*; and **its `--offline-input` named `evidence/session-44-offline.json`, the local gate's half at `c947180`**, not 224b660's. | The offline half was corrected before the merge: CI contract run 39801089169's artifact `session-01-evidence` carries `evidence/session-44-offline.json` (checkout `224b660`, 155/155, sha `4e6c70a8`), placed as the input; the local half kept as `session-44-offline-c947180.json`. The rest is cosmetic; the walker prefix is derived from the session at Run 9. | A derived script's literals are read whole before it runs, not only its substitutions. | — |
| **D2805** | Run 8's D2797: *"NOT DIAGNOSED"*; the site's idle-sleep sentence (*"sleep after 15, 30 or 60 minutes with no request and no connection"*); ADR 0276. | **Diagnosed at the close** (Sheet IR, a root read-only query of the control database): after attempt 1's wake at 17:12Z the samples read `requests_counter` 3 once more (17:15:39), then **`unread` for 51 min** (17:20:45–18:11:38), reason *"the store holds no request answered below 400"* (`bin/reconciler.py:1504`, `store_value`'s `empty=`). The wake recreated the project's services, the old series went stale, and nothing answered a request below 400 after it, so the store held no series; `app.control_request_idle_sleep` fails closed on an unread counter (D2525). Customer activity was quiet from 17:46Z, no operation finished after 17:19Z, the samples were contiguous. Attempt 1 slept because the instrument made requests after its 16:31 wake. | **A product finding, not repaired at the close** (a release): **a project woken and then left untouched is never idle-slept** -- an absent series is read as unread, not as zero, while D2539 decided the same question for customer activity the other way. The site's sentence does not hold in that case. Session 45 decides it. | A counter that exists only after its first event cannot tell *none* from *unknown* by its absence; the reader must decide which one absence means, on purpose. | 0276 |
| **D2806** | Run 9 step 1: *"`sql_editor` → `beta` if …; no row `trial` at the close"* (ADR 0261); §7. | The tagged evidence also failed **`notifications_retrial_live`**, the evidence of the `beta` row `notifications` (D2798), so the Ledger guard fails against `evidence/session-44.json`. Moving it to `planned` (Session 41's D2557 precedent) meets two readers Session 41 did not have: **the console's notifications view** (`pages.json`, `test_console_pages.py:95` -- every page's rows reachable) and **the site's `plans-and-usage` page** (`site_build.check_page`). | **The operator chose `planned` and the views removed**: `notifications` `planned`, target 45, evidence and controls empty; the console's org tab, view and route removed (`app.js`, `pages.json`) -- on `main`, undeployed: the 1.22.0 console still shows it until Session 45's release; the site's section, its CLI-table row and its index mention removed (the site redeploys on push); the `console` row's customer text no longer lists notifications. The CLI's `apg notifications list` stays (published in 1.22.0). `sql_editor` → `beta` (D2807). | A Ledger row a page names cannot be demoted alone; the close reads every page's `ledger` list before it moves a row. | 0261 |
| **D2807** | Run 8's D2799 (*"the offline fixture shared the proof's belief"*); Run 8 step 6, the merge. | **D2799's cause sentence was wrong**: `test_session44_sql_editor.py` has no offline reader -- the plan excluded it from X0, so the external half was its first execution at all. Repaired at **`e8f0eaa`** (test-only: `_pooled` reads the deployed route `{status, url}`, status `ready`); GREEN live with `-k` against `224b660` (the three refusals and the policy control, 4 passed). | **The operator chose to re-run the external half** (Session 42's D2645 precedent): from `e8f0eaa` against the deployed `224b660` (07:18–07:30Z), 129 passed, 2 failed (the notification proofs); **merged 331: 328 passed, 3 failed**, `source_commit` = `offline_checkout_commit` = `224b660`; nothing outside `docs/` and `tests/` moved since `224b660`. Run 8's first external half and merge kept in `~/s44/run8/external-1/`. `sql_relay_live` passed → `sql_editor` **`beta`**. | A module a plan excludes from its rehearsal is first executed by the evidence run; the plan names that as a risk and rehearses it with `-k` against the live deployment before the sweep. | — |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**One new family, `SQL`** (the stage plan's proposal, `:1051`): the regex at
`tests/contract/test_acceptance_registry.py:128` gains `SQL`, and the family
comments gain one sentence after Session 43's (`:126-127`): *Session 44 (ADR
0285-0286) adds `SQL` for the browser SQL editor and its relay.* No existing
prefix begins `SQL` (§0: none), so nothing collides. **Nine requirements, nine
claims, all `target_session: 44`, all P0 — six offline, one host, two
external.** Node ids are **proposed; Run 7 writes what the runs actually
wrote**, read with `pytest --collect-only -q` (D1236, D2129). Committed by Run 7
with the constant (D690), under **`# Session 44 (ADR 0285-0286)`** after `:8300`.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `SQL-CLIENT-001` | The console's wire client: the startup message exact; SCRAM-SHA-256's proof equal to a Python reference for a fixed nonce and salt; a forged server signature refused; any other authentication refused; a query's rows and an error's fields read from PostgreSQL 18.4 through PgBouncer; COPY refused; a cancel stops a running statement; the 1,000-row cap cancels | `tests/contract/test_console_pg.py::test_the_startup_message_is_exact`, `::test_the_scram_proof_equals_pythons`, `::test_a_forged_server_signature_is_refused`, `::test_only_scram_is_spoken`, `::test_a_query_returns_its_rows`, `::test_an_error_names_its_code`, `::test_copy_is_refused`, `::test_a_cancel_stops_the_statement`, `::test_the_row_cap_cancels` | — (`sql_client`) |
| `SQL-RELAY-001` | The relay's admission: a foreign or absent `Origin` refused before the upgrade; only a door name in the grammar accepted; an address, a port, a query or another path refused before any TCP; the grammar agrees with `naming` | `tests/contract/test_sql_relay.py::test_a_foreign_origin_is_refused_before_the_upgrade`, `::test_no_origin_is_refused`, `::test_only_a_door_name_is_accepted`, `::test_an_address_or_a_port_is_refused`, `::test_the_grammar_agrees_with_naming` | — (`sql_relay_admission`) |
| `SQL-RELAY-002` | The relay's bounds: the 33rd session, the 5th per door and the 5th per source refused `4429`; idle 300 s and total 1,800 s closed `4408`; a message over 1 MiB closed; the 64 MiB and 64 KiB caps close `4413`; it pings | `tests/contract/test_sql_relay.py::test_the_ceilings_refuse_the_next_session`, `::test_an_idle_session_is_closed`, `::test_a_session_is_closed_at_its_total`, `::test_a_large_message_is_refused`, `::test_the_byte_caps_close_the_session`, `::test_the_relay_pings` | — (`sql_relay_bounds`) |
| `SQL-RELAY-003` | The relay holds and records nothing: no line holds a password, a SASL message, a statement or a row (the canary); it reads no secret and no file; the door is verified (a wrong CA refused `4502`); an unreachable door is reported unreachable, never asleep | `tests/contract/test_sql_relay.py::test_no_line_holds_the_payload`, `::test_the_relay_reads_no_secret_and_no_file`, `::test_the_door_is_verified`, `::test_an_unreachable_door_is_reported_unreachable` | — (`sql_relay_holds_nothing`) |
| `SQL-PLANE-001` | The `sql-relay` service: bounded, read-only, uid 65532, no secret, no mount, network `edge` only, profile `sql-relay` added only for the control project, its router rule exactly ``Host(`<relay host>`)``, `websockets` pinned in `versions.env` and imported by the image's build | `tests/contract/test_process_limits.py::test_the_sql_relay_is_bounded`, `tests/contract/test_sql_relay_plane.py::test_the_profile_is_added_only_for_the_control_project`, `::test_the_router_rule_is_the_relay_host_alone`, `::test_the_relay_holds_no_secret_and_no_mount`, `::test_the_names_are_derived`, `tests/contract/test_version_lock.py::test_websockets_is_locked` | — (`sql_relay_plane`) |
| `SQL-PAGE-001` | The editor page: the CSP admits `'self'` and the relay's origin alone; only `pg.js` opens a WebSocket; the password is never stored, put in a URL or sent to `/v1`; an asleep project opens no socket; a project with no door shows no control; the view maps to reachable rows | `tests/contract/test_console_server.py::test_the_policy_admits_the_relay_alone`, `::test_a_bad_relay_origin_refuses_to_start`, `tests/contract/test_console_pages.py::test_only_pg_js_opens_a_websocket`, `tests/contract/test_console_sql.py::test_an_asleep_project_opens_no_socket`, `::test_a_project_without_doors_shows_no_editor`, `::test_the_password_reaches_only_the_socket` | — (`sql_editor_page`) |
| `SQL-HOST-001` | On the host: the relay runs on `control-prod` only, bounded, healthy; the listeners did not change; its log holds the walk's marker nowhere; its peak memory read | — | `tests/deployment/test_session44_sql_relay_host.py::test_the_relay_runs_only_on_the_control_project`, `::test_the_relay_is_bounded`, `::test_the_listeners_did_not_change`, `::test_the_relay_logged_no_payload` (host `sql_relay_host`) |
| `SQL-LIVE-001` | Through the public origins with no SSH: a member signs in, opens `slot3-prod`'s editor, connects to each door as that door's role with the password from its file, runs statements; PostgreSQL refuses `app_private` (`42501`); a cancel stops `pg_sleep` (`57014`); 5,000 rows are capped at 1,000; the role's connections stay within its limit; the times recorded | — | `tests/external/test_session44_sql_editor.py::test_the_editor_walk_reached_every_step`, `::test_each_door_answered_as_its_role`, `::test_postgres_decided_the_refusal`, `::test_the_cancel_stopped_the_statement`, `::test_the_rows_were_capped`, `::test_the_role_stayed_inside_its_limit`, `::test_the_times_were_recorded`, `::test_this_module_uses_no_ssh` (external `sql_editor_live`) |
| `SQL-LIVE-002` | Live: the relay refuses a foreign `Origin` (403), a name outside the grammar (400), reports an unrouted door name `4502`; the console's answers carry the policy naming the relay's origin; the relay's certificate names its host | — | `tests/external/test_session44_sql_editor.py::test_a_foreign_origin_is_refused_live`, `::test_a_name_outside_the_grammar_is_refused_live`, `::test_an_unrouted_door_is_unreachable_live`, `::test_the_console_policy_names_the_relay`, `::test_the_relay_certificate_names_its_host` (external `sql_relay_live`) |

**Expected counts** — Run 7 counts them from the tuples, never from this prose
(D1628): requirements **415 → 424**, `CLAIMS` **322 → 331**, `OFFLINE_CLAIMS`
**149 → 155**, ADRs **284 → 286**.

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, a block commented
*Session 44 (ADR 0285-0286)* after Session 43's `:1003-1027`): offline —
`sql_client`, `sql_relay_admission`, `sql_relay_bounds`, `sql_relay_holds_nothing`,
`sql_relay_plane`, `sql_editor_page` — **these six** go in `OFFLINE_CLAIMS`
(after `:516`) with the per-session assertion in
`test_session_forty_four_gate_modes.py` (D1237: assert THESE are in the set,
never its size). Host — `sql_relay_host`. External — `sql_editor_live`,
`sql_relay_live`. `CLAIM_INTRODUCED_IN` (`test_evidence_claims.py:953-1365`)
gains a row at 44 for each.

**Existing entries that move** (each a passing proof made stricter or its
fixture changed under ADR 0285 — CLAUDE.md §6):

- **`CON-SERVE-001`**: `test_every_answer_carries_the_policy` reads the policy
  built for the fixture relay origin (D2744); `test_only_the_listed_paths_answer`
  lists `/console/pg.js`.
- **`CON-PLANE-001`**: `test_the_console_holds_no_secret_and_no_mount`'s
  environment set gains `APG_CONSOLE_SQL_RELAY_ORIGIN` (exactly three names).
- **`CON-SCRAM-001`**: `test_every_script_parses`' name list gains `pg`.
- **`CON-LEDGER-001`**: the `sql_editor` exception added in Run 5, removed in
  Run 7 (D2746).
- **`SITE-CLAIM-001`**: `test_site.py:165`'s fixture `sql_editor` → `passkeys`
  (Run 7, D2745).
- **The record-reading external modules** (D2748, D2749): their `session`
  tuples gain 44 (Run 6, count-asserted); **their `source_commit` checks are
  untouched**.
- **`THR-*` rows**: five added in Run 7 (D2753); none removed.

**New environment gates: one** — `APG_SQL_EDITOR_RECORD_FILE` (D2752), in the
roster `tests/conftest.py:86-232` after `:231`, exported by the gate's external
mode. **Read in a test body with `.get(...)`, never `x["APG_…"]`** (D2381).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| **An A record `sql.agenticpostgresql.com` → 15.204.231.45, DNS-only** | Sheet D0 (Run 1, the agent) | The operator's decision (D2733); the zone listed first (no `sql` record may exist — else §9's stop); `proxied: false` read back; a name nothing routes yet answers the edge's 404 |
| `CURRENT_SESSION` 43 → 44; `VERSION` 1.21.0 → 1.22.0; `sql_editor` → `trial`; THR rows; the site's editor page | Run 7 | All-or-nothing (D690); `README.md:7` and every `--session 43`/`--through-session 43` literal on the documented path moved and counted per file (D678/D1484); ADRs 0261, 0285 |
| `bin/session-44-check.sh` | Run 7 | Derived from 43's by diff (D1482); header and usage rewritten whole (D1488); one flag (D2752); `SHELL_COMMANDS`; `chmod 755` before `git add` |
| **1.22.0 deployed on the four projects — every database restarted once; the relay started on `control-prod`; its certificate issued** | Sheets R2a–R2d (Run 8) | The reconciler stopped (D2178); one project at a time, each window probed; control-prod last (the relay and its ACME issuance with it — read once, never retried in a loop); the restart named on each sheet (D2747) |
| **`slot3-prod`'s `customer_app` password rotated again by the console walk** | Run 8 (W1′) | The probe organisation's own project; the old creds file kept as `.before-s44`, the new written 0600 by the instrument; `customer_admin` untouched (D2749) |
| **A walker account `walk-s44-…` and its membership in `probe-s37`** | Run 8 (W0′, W1′) | Membership removed after; accounts are never deleted (D2065) |
| **`slot8-prod` declared, provisioned, created, slept, woken, resized, exported, deleted — consumed** | Run 8 (H1 … SL4) | Session 43 Run 10 step 4b's sheets, renamed (D2748); a slot is never reused; its identity revoked after the tag |
| Tag `1.22.0` on the deployed commit | Run 8 | After the merge exits 5 for `documented_path` only (§7); from the WORKSTATION (D2041) |
| **`agentic-postgres-cli 1.22.0` published to PyPI** | Run 8, by the tag | `publish-cli`'s `verify` reads that SHA's `contract` success; a PyPI version is never re-uploaded |

---

## 5. Build order, run by run

Each run ends with a `**Done.**` paragraph written by the executor: what was
measured, the numbers, the rows it added, and — for a code run — the CI verdicts
by full SHA (`contract` and `site`). The targeted modules run ONCE at the run's
close and only a failing module is re-run. `ruff format && ruff check` before
every commit; `chmod 755 bin/*.sh bin/*.py deploy.sh libexec/*` before every
`git add` — **and every file an image executes directly** (D2412); messages from
a file with `-F`, ending with the attribution lines the session's system reminder
gives. **Grep the plans for every third party before measuring it.** **A run
that renames, adds or removes a test function runs `test_acceptance_registry`
and `test_evidence_claims`** (D1119); **a run that adds a module under
`src/agentic_postgres/` runs `test_repository_contract`** (D2114 — this session
adds none: the names go into `naming.py`); **a run that adds a `document[...]`
read to a `bin/` command runs `test_container_selectors`** (D1184); **a run that
touches a documentation page runs `test_documentation_index` and
`test_session12_documented_path`**; **a run that touches `.github/workflows/`
runs `test_gate_contract`** (none planned); **a run that touches
`versions.in.yaml` runs `test_version_lock` and `bin/lock-versions.sh --check`**;
**every new test module carries `pytestmark` before its first test** (D1240),
and the sweep-selector guard (D1242) AND `test_environment_gates` join the
targeted list of any run that adds a module — **read a model dict with
`.get("APG_…")`, never `x["APG_…"]`** (D2381). **Docker-backed modules reuse
`tests/contract/control_cluster.py`** (`docker rm -fv`, D2098). **Every external
fixture that holds a password, verifier, token or TOTP seed returns
`tests/external/redaction.py`'s `Secret`** (D2420). **Never print a live log's
failure body without filtering it by the secret VALUES** (D2416). **Every
mutation battery** follows CLAUDE.md §1: `PYTHONDONTWRITEBYTECODE=1`, snapshot to
`/tmp` and restore by copy with `cmp`, anchors pre-flighted (a miss fatal), a
control the mutation cannot reach, and *how* each failed (`FAILED` vs `ERROR`).
**Never put `--` inside a SQL string literal in a migration template, and never
backticks in an inline heredoc.** **A JavaScript test runs the file in the pinned
`NODE_RUNTIME_IMAGE`** (`versions.env:18`; Node 22 has `WebSocket` and
WebCrypto as globals — rig 44b reads both), the way `test_console_scram.py`
already does.

### Run 1 — the relay's name, the rigs, the threat items, ADRs 0285–0286

**Documentation, one agent act on the zone; no code; no CI read.**

**Read first:** this plan §0 and §1 whole; ADRs 0246, 0268 (whole), 0269, 0280,
0281; `services/console/serve.py` and `public/api.js`, `scram.js` whole;
`docs/threat-model.md:190-201` (the preamble) and `:395-459` (items 16–21, the
shape to copy); `docs/decisions/README.md:300-350`; `grep -n "WebSocket\|wss:\|relay"
docs/plans/stage-5-plan.md` (the explore pass's hits; nothing earlier measured a
WebSocket).

**Step 1 — Sheet D0 (the agent; D2733).** Through the Cloudflare API (the
`cloudflare-api` MCP tool; re-auth with `/mcp` if it says so): the zone id by
name; `GET /zones/{zone}/dns_records?per_page=100` — **stop (§9) if any record
named `sql.agenticpostgresql.com` exists**; `POST` one `A` record `sql` →
`15.204.231.45`, `proxied: false`, TTL auto, comment *"apg sql relay (Session
44, D2733)"*; read it back; read every other record unchanged (Session 43's 28
plus `slot7-prod`'s three greys, all `proxied: false` but the two Pages
CNAMEs). `nslookup sql.agenticpostgresql.com 1.1.1.1` → `15.204.231.45`;
`curl -sI https://sql.agenticpostgresql.com/` → **no certificate for the name
yet** (the edge has no router for it; recorded as read, whatever it is).

**Step 2 — the apt pins (D2747).** The two index reads the comments at
`versions.in.yaml:576-603` and `:616-642` give, in a throwaway
`debian:bookworm-slim` container: `ca-certificates 20250419~deb12u2` and
`pgbackrest 2.59.3-1.pgdg12+1` present → recorded; **either absent → a row, and
Run 2 repins by D2731's method first**.

**Step 3 — the rigs**, each in its own throwaway directory under `~/s44/rigs/`
on WSL, each with its control, each result written to `~/s44/rigs/<rig>.txt` as
it is taken. **Rig 44d runs first** (the others use its pinned `websockets`).

- **Rig 44d — `websockets`** (D2742). `https://pypi.org/pypi/websockets/json`:
  the newest release ≥ 14 days old, its licence, `requires_dist` for Python 3.12
  (expected: none), the sha256 of the `cp312 manylinux x86_64` wheel and the
  sdist. In a throwaway container from `PYTHON_RUNTIME_IMAGE`: `pip install
  websockets==<v>`; a 30-line `websockets.asyncio.server.serve(handler, …,
  origins=["https://a.test"], max_size=1<<20, ping_interval=20,
  process_request=…)`; a raw client (stdlib `socket`, a hand-written upgrade)
  sending `Origin: https://b.test` → **`403` before any `101`** (the
  **control**: `Origin: https://a.test` → `101`); a 2 MiB message → close
  `1009` (control: 1 MiB passes); `process_request` returning a `400` for a bad
  path → no `101`. Recorded: the version, the hashes, the readings.
- **Rig 44a — the WebSocket through Traefik in a real browser** (D2741, D2744,
  D2751). In a Docker network on the workstation: **Traefik from
  `TRAEFIK_IMAGE`** with an entrypoint copied from `infra/edge/traefik.yaml:94-100`
  (`websecure`, the same `respondingTimeouts`) and a file-provider TLS store with
  a rig CA's certificate for `relay.test` and `console.test`; a router
  ``Host(`relay.test`)`` → rig 44d's server (a 20-line echo-and-count handler);
  a router ``Host(`console.test`)`` → a static page server setting `__Host-c=1;
  HttpOnly; Secure; SameSite=Strict; Path=/` and the header `Content-Security-Policy:
  default-src 'none'; script-src 'self'; connect-src 'self' wss://relay.test`;
  the rate-limit middleware of `baseline.yaml:50-58` on both. **Chromium in the
  pinned Playwright image** (`mcr.microsoft.com/playwright/python:v1.63.0-noble@sha256:72bd171a…`,
  present; the package from `tests/external/browser/requirements.txt` by
  `--target`, D2686), host-resolver rules mapping both names to Traefik,
  `ignore_https_errors` off and the rig CA trusted. **Measure**: (1) the page's
  `new WebSocket("wss://relay.test/v1/door/x")` reaches the handler with
  `Origin: https://console.test` and **no `Cookie`** (the **control**: a
  WebSocket to `wss://console.test/…` carries `__Host-c`); (2) a WebSocket to
  `wss://other.test` is **blocked by the CSP** (a `securitypolicyviolation`
  event, no request at Traefik); (3) binary frames round-trip byte-exact; (4)
  sessions idle 150 s **without** pings, **with** 20 s pings, and **streaming**
  a frame a second for 150 s — which survive Traefik's 30/30/60 s (D2751); (5)
  100 frames a second for 5 s on one socket draw no 429 (control: 100 plain
  `GET`s a second draw 429s) — the limit counts the upgrade only; (6) the
  handler's `X-Real-Ip` and `X-Forwarded-For` when the client sends its own
  `X-Forwarded-For: 203.0.113.9` — **overwritten or appended** (D2741 decides
  the per-source ceiling from this reading); (7) under **32 concurrent
  sessions** streaming 1 KiB frames for 60 s, the relay container's
  `docker stats` memory and pids peaks (the control: 0 sessions) — D2750's
  workstation reading.
- **Rig 44b — the wire client against PostgreSQL** (D2732, D2754, D2755). A
  prototype `pg.js` (Run 4's starting point, kept in the rig directory, not
  committed) run **in Chromium** (rig 44a's page) **and in Node 22**
  (`NODE_RUNTIME_IMAGE`) through rig 44d's relay to **PostgreSQL from
  `POSTGRES_IMAGE`** (`ssl=on`, a rig-CA certificate for `pool.test`) behind
  **PgBouncer from `PGBOUNCER_IMAGE`** in `pool_mode = transaction` with a SCRAM
  userlist (the `customer-pool` shape, `compose.yaml:798-819`), and a second in
  `session` mode. The relay does SSLRequest + TLS (SNI `pool.test`, ALPN
  `postgresql`) — **through a rig Traefik TCP router** with ``HostSNI(`pool.test`)``
  and `baseline.yaml:31-35`'s TLS option, PgBouncer behind it in plaintext (the
  door's real shape). **Measure**: (1) SCRAM-SHA-256 succeeds and the
  client-final proof equals Python's `hashlib`/`hmac` computation for the logged
  nonce and salt (the **control**: a wrong password → `ErrorResponse` `28P01`);
  (2) a tampered server-final (the relay rig flips one byte of `v=`) → the
  client refuses before `AuthenticationOk` (the control: untampered passes); (3)
  `SELECT 1; SELECT 1/0` → one result then `22012`; (4) `COPY (SELECT 1) TO
  STDOUT` and `COPY t FROM STDIN` handled without a hang; (5) **a CancelRequest
  as a second relay session stops `SELECT pg_sleep(30)` with `57014` within
  5 s** in both pool modes (the control: no cancel → it completes); (6)
  `SELECT generate_series(1, 200000)` with the 1,000-row cap → the cap's cancel
  ends it and the socket stays usable; (7) Chromium's `crypto.subtle` PBKDF2 /
  HMAC / SHA-256 equal Node's for the same inputs. **If (1), (2) or (5) fails:
  §9's stop.**
- **Rig 44c — the relay's TLS to the door** (D2739). In
  `PYTHON_RUNTIME_IMAGE`: `ssl.create_default_context()` reads a trust store
  (`/etc/ssl/certs/ca-certificates.crt` present — recorded); the relay's
  SSLRequest-then-wrap with `server_hostname=<name>`,
  `set_alpn_protocols(["postgresql"])` against rig 44b's Traefik: verified with
  the rig CA added (**control**: without it → `CERTIFICATE_VERIFY_FAILED`);
  SNI `unknown.test` → EOF in the handshake (ADR 0268 `:68`'s shape) → the relay
  maps it to `4502`. **Then, read-only, against the live door from WSL** with
  the same code and the system trust store: `pool.slot3.agenticpostgresql.com`
  verified, `pool.slot99.agenticpostgresql.com` → EOF (no DNS lookup: the code
  connects to `15.204.231.45:5432` with the name as SNI — the address the relay
  will never use, read here only because the workstation is not on the edge's
  network).
- **Rig 44e — the console's script in Node with a fake `api.js`** (D2757). The
  shape Run 5's `test_console_sql.py` needs: Node 22 runs an ES module that
  imports a stub `api.js` and a stub `WebSocket`, and a minimal DOM is not
  available — **read whether the editor's logic can be a DOM-free module**
  (`sql.js`: state → decision) with `app.js` only rendering. Recorded: the
  module boundary Run 5 uses.

**Step 4 — the threat items** (D2753). `docs/threat-model.md`'s hosted list
gains **items 22–26** after item 21 (`:452-459`), each with its threat, the
control this session builds and the test that holds it: **22 The relay as an
open proxy** (it reaches only names in the grammar, through the edge's
`sniStrict`, which a stranger already reaches on 5432; `Origin`; refused before
any TCP), **23 The customer's password in the page** (CSP `connect-src 'self'
<relay>` — nowhere else to send it; no third-party script; a closure, never
storage, a URL or `/v1`; SCRAM, so neither the relay nor the door sees it;
THR-CON-XSS's controls), **24 Exhaustion of the relay or a project's
connections** (the relay's ceilings; the role's `CONNECTION LIMIT` enforced by
PostgreSQL and PgBouncer unchanged; idle and total limits; the edge's rate limit
on upgrades), **25 The relay can read what it carries** (what it can read: SQL,
rows, the SASL exchange; it records none — offline and live canaries; a captured
exchange admits an offline guess only against a weak password, and the console
and CLI generate 32-byte ones — **a verifier a customer computes from a weak
password through the raw API is the customer's risk, said in the editor's
documentation**), **26 A statement with no deadline** (no `statement_timeout` on
the customer roles, D2735; the editor's 60 s cancel; the relay's 30 min; `psql`'s
same gap named, not closed).

**Step 5 — ADRs 0285–0286** (`docs/decisions/0285-…md`, `0286-…md`), indexed in
`docs/decisions/README.md` after `:350`, each with Context, Decision,
Alternatives, Consequences in the shape of 0280–0284:

- **0285 — The browser SQL editor is the customer's own client: an in-house
  wire-protocol client in the console, the password held only in the page.**
  D2732, D2734 (ADR 0246's sentence amended, verbatim; ADR 0246 gains *"Amended
  by ADR 0285"*), D2735, D2737, D2738, D2744 (ADR 0280's constant amended — the
  exact template), D2745, D2746, D2754–D2757; rigs 44a/44b/44e; alternatives:
  vendored TLS-in-WebSocket (rejected by the operator, D2732 — what it would
  have bought: the relay blind), a server-side SQL endpoint (ADR 0246, never),
  Studio hosted (ADR 0205).
- **0286 — The SQL relay: a bounded WebSocket-to-door service on its own name
  that authenticates nothing, holds nothing, reaches only door names through the
  edge, and records none of what it carries.** D2733, D2736, D2739–D2743, D2751;
  rigs 44a/44c/44d; every constant (32/4/4, 300 s/1,800 s, 1 MiB/64 MiB/64 KiB,
  20 s pings, the close codes `4400 4403 4408 4413 4429 4502`); the log line's
  exact shape; alternatives: a same-origin path (rejected by the operator,
  D2733), a per-project relay, a relay that checks the console session
  (it would have to hold a verification key and receive a token; the door is
  public anyway), Traefik alone (no WebSocket-to-TCP).

**The console's Content-Security-Policy after ADR 0285** (Run 5 implements it
as one function of one rendered origin):

```
default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:;
connect-src 'self' wss://sql.agenticpostgresql.com; font-src 'none';
base-uri 'none'; form-action 'none'; frame-ancestors 'none'
```

**Done.** (2026-10-21, 18:14–18:40Z; documentation only — pushed, no CI read.)

- **Sheet D0** (the agent, the Cloudflare API, zone `5f7560988cc4d6d45c29425f6365ef0e`):
  33 records listed, **none named `sql`** (D2759: the plan's count omitted the two
  slot3 branch wildcards); `A sql.agenticpostgresql.com → 15.204.231.45`,
  `proxied: false`, TTL 1, comment *"apg sql relay (Session 44, D2733)"*, **record
  id `af246339104e95bba082ecfbc7f510ae`**, created 18:14:02Z, read back; 34
  records after, the two Pages CNAMEs the only proxied ones. `nslookup … 1.1.1.1`
  → `15.204.231.45`. `https://sql.agenticpostgresql.com/` → curl 35, TLS alert
  `unrecognized_name` (D2760).
- **The apt pins** (`~/s44/rigs/pins.txt`, 18:14:48Z): pgdg lists `2.59.3-1.pgdg12+1`
  (and 2.59.2, 2.59.1 — D2761); bookworm-security lists `20250419~deb12u2`. **Both
  present; nothing repinned.**
- **Rig 44d** (`~/s44/rigs/44d/`): `websockets` **17.2** (2026-10-03, 18 days;
  17.3 two days old), BSD-3-Clause, **no `requires_dist`**, wheel
  `sha256:6627b913…268a5b`, sdist `sha256:36c2fb94…dc8792`. Foreign `Origin` →
  `403`, no `Origin` → `403` (control: listed → `101`); 2 MiB → `1009`
  (control: 1 MiB echoed); bad path → `400`; **`process_request` runs before the
  `origins` check, and the library logs tracebacks on its own logger** (D2762).
  No stop.
- **Rig 44a** (`~/s44/rigs/44a.txt`; Traefik 3.7.10, Chromium from the pinned
  Playwright image, the rig CA trusted through `--ignore-certificate-errors-spki-list`
  with `ignore_https_errors` OFF — the image has no `certutil`; control: a
  certificate from an unrelated key → `ERR_CERT_AUTHORITY_INVALID`; the rig's
  entrypoints bound to 443/5432 inside its network, the timeouts copied
  verbatim): (1) the relay saw `Origin: https://console.test` and **no
  `Cookie`** (control: `__Host-c=1` to the console host); (2) a WebSocket to an
  unnamed host → `connect-src` violation, **0 requests at the edge**; (3)
  65,792 bytes byte-exact; (4) **all four 150 s sessions survived**, idle with no
  pings included (D2763 — no stop); (5) 500 frames in 5 s all echoed (control:
  100 GETs → 43 × 200, 57 × 429); (6) client `X-Forwarded-For`/`X-Real-Ip`
  **overwritten** by the edge (D2764); (7) 32 sessions × 60 s streaming 10 KiB/s
  each: rig relay **19.5 MiB / 3 pids** peak (control 18.8 MiB / 3) — the
  workstation's reading; (8) an upgraded session logs `DownstreamStatus: 0`.
- **Rig 44b** (`~/s44/rigs/44b.txt`; the prototype `pg.js`, `suite.mjs`,
  `pgrelay.py` kept in `~/s44/rigs/44b/` for Runs 2 and 4; PostgreSQL 18.4,
  PgBouncer 1.24.1 transaction + session, Traefik TCP router with the `postgres`
  option; Node 22.23.2 and Chromium): SCRAM authenticated and **the proof equals
  Python's in both runtimes**; wrong password → **`08P01`** (D2765); tampered
  `v=` → refused before `AuthenticationOk`; `22012` after one result; COPY
  out dropped, COPY in → `CopyFail` → `57014`, 0.01 s; **cancel → `57014` in
  1.05–1.08 s** in both modes (control `pg_sleep(3)` completed 3.01 s); the cap:
  a fast statement finished first, a producing one was ended `57014` at ~1,380
  rows in 1.8 s (D2766); the crypto vector equal in Chromium, Node and Python;
  the role's connections 1–2 against its limit 2. No stop. (Postgres ran
  without `ssl=on`: the door terminates TLS at Traefik and PgBouncer speaks
  plaintext to the cluster, as on the host.)
- **Rig 44c** (`~/s44/rigs/44c.txt`): `/etc/ssl/certs/ca-certificates.crt`
  present in `PYTHON_RUNTIME_IMAGE`; rig door verified with the rig CA (TLSv1.3,
  ALPN `postgresql`), control without it → `unable to get local issuer
  certificate`; `unknown.test` → EOF → `4502`; a router whose backend does not
  resolve also answers no TLS. **Live door with the image's own store:
  `pool.slot3…` and `direct.slot3…` VERIFIED** (TLSv1.3, ALPN `postgresql`, one
  certificate `CN=pool.slot3.agenticpostgresql.com`); `pool.slot99…` → EOF. No
  stop.
- **Rig 44e** (`~/s44/rigs/44e.txt`): a DOM-free `sql.js` with injected `call`
  and `connect` runs in the pinned Node image; all nine states walked (asleep
  three → no socket; `ready`/`updating` → one, the password reaching only
  `connect`); `409` → not offered; the control, a DOM-touching module →
  `ReferenceError: document is not defined` (D2768, D2770).
- **Threat items 22–26** appended to `docs/threat-model.md`'s hosted list.
- **ADRs** `docs/decisions/0285-the-browser-sql-editor-is-the-customers-own-client-an-in-house-wire-protocol-client-in-the-console.md`
  and `0286-the-sql-relay-is-a-bounded-websocket-to-door-service-on-its-own-name-that-authenticates-nothing-and-records-nothing-it-carries.md`,
  indexed; ADR 0246's and ADR 0280's status lines and index rows name 0285.
  `test_every_adr_is_indexed` and `test_the_index_status_agrees_with_each_adr`
  run once: 2 passed.
- Rows **D2759–D2770**. **NEXT FREE D2771, ADR 0287.**

### Run 2 — the relay (`services/sql-relay/`, `versions.in.yaml`, tests)

**Read first:** ADR 0286; rigs 44a/44c/44d's files; `services/console/Dockerfile`
whole and `services/auth-api/Dockerfile:1-32,75-93` (the pin pattern);
`versions.in.yaml:460-467` (`SEGNO_VERSION`, the entry to copy);
`bin/lock-versions.sh` `--help`; `tests/contract/control_cluster.py` (the
Docker-backed fixture pattern); `tests/contract/test_console_server.py` (the
shape of a server's tests).

1. **The pin**: `WEBSOCKETS_VERSION` in `versions.in.yaml` `packages:` (rig 44d's
   version and digest), `bin/lock-versions.sh --update --packages-only` → the
   diff is exactly the two `versions.env` lines; `--check` passes.
   `tests/contract/test_version_lock.py::test_websockets_is_locked` (Session
   43's `test_segno_is_locked` shape — read it first).
2. **`services/sql-relay/relay.py`** (stdlib + `websockets` only): the
   constants of ADR 0286 at the top; the environment read once at start
   (`APG_SQL_RELAY_PORT` 8080, `APG_SQL_RELAY_ALLOWED_ORIGIN`,
   `APG_SQL_RELAY_ZONE`, `APG_SQL_RELAY_UPSTREAM` `host:port`) — **a missing or
   malformed value refuses to start**; `process_request`: `GET /__apg/healthz` →
   `200 {"status":"ok"}`; the path grammar (D2740) and the ceilings (D2741) → an
   HTTP refusal before the upgrade; `origins=[ALLOWED_ORIGIN]` (rig 44d); the
   handler: register the session, open TCP to the upstream (`asyncio.open_connection`,
   5 s), SSLRequest (8 bytes `00000008 04d2162f`), read one byte (`S` or close
   `4502`), `loop.start_tls` with the context of D2739 and SNI = the door host,
   then two pumps (browser → door: binary frames only, a text frame closes
   `4400`; door → browser: chunks ≤ 64 KiB as binary frames), the byte caps, the
   idle and total timers, and **one log line at the end** (D2743). Bytes the
   browser sends before the door is ready are held up to 64 KiB.
3. **`services/sql-relay/Dockerfile`**: `ARG PYTHON_BASE_IMAGE`,
   `ARG WEBSOCKETS_VERSION` (no defaults), `pip install --no-cache-dir
   "websockets==${WEBSOCKETS_VERSION}"`, `python -c "import websockets"`, uid
   65532, `COPY relay.py`, `EXPOSE 8080`, a `HEALTHCHECK` through `urllib`
   (compose's form wins, as the console's does), exec-form entrypoint.
4. **Tests** `tests/contract/test_sql_relay.py` (`pytestmark` first): pure tests
   of the grammar (with `naming`'s agreement — D2740), and **Docker-backed
   tests** that start PostgreSQL (`POSTGRES_IMAGE`, `ssl=on`, a test CA made in
   `tmp_path`) and the relay **in-process** (`asyncio`, the upstream pointed at
   the database container, the CA file passed by a test-only argument that the
   image never reads — **a guard proves the image's entrypoint passes none**), and
   a raw-socket WebSocket client (no new dependency in the dev lock — the
   client is ~60 lines in the test's helper; `websockets` is already in the dev
   lock as a transitive and MAY be used, `requirements-dev.txt:1373`; the run
   decides and records which). Every §2 node id of `SQL-RELAY-001`–`003`. The
   idle/total tests use the constants patched small (the patch named in the
   test, never the module's value).
5. **Battery** (`~/s44/run2/battery2.py`): the `Origin` check removed; the
   grammar's anchor dropped (`.search` for `.fullmatch`); the per-door ceiling
   +1; the idle timer never armed; the verify mode `CERT_NONE`; a log line
   gaining the first 32 bytes of a frame — each **FAILED** by its named test,
   the control (a test the mutation cannot reach, `test_the_grammar_agrees_with_naming`
   for the first five) PASSED, every file restored by `cmp`.

Targeted: `test_sql_relay`, `test_version_lock`, `test_repository_contract`,
`test_environment_gates`, the sweep-selector guard. Commit, push, read CI.

**Done.** (2026-10-21; WSL `~/s44/run2/`.)

- **The pin (D2771):** `WEBSOCKETS_VERSION` 17.1 in `versions.in.yaml` (after
  `SEGNO_VERSION`, its reasons in the comment); `bin/lock-versions.sh --update
  --packages-only` → `WEBSOCKETS_VERSION=17.1`,
  `WEBSOCKETS_VERSION_DIGEST=sha256:acfea4c2…` (the sdist), the header's input
  hash and stamp, 15 images carried forward; `--check` passes.
  `tests/contract/test_version_lock.py::test_websockets_is_locked`.
- **`services/sql-relay/relay.py`** (stdlib + `websockets`): ADR 0286's
  constants at the top; `configuration()` refuses a missing or malformed value
  (exit 2, one stderr line, before any socket); `process_request` — health,
  then `Origin`, then the door grammar (D2773); the ceilings after the upgrade
  (`4429`); upstream SSLRequest + TLS with SNI, ALPN `postgresql` and the
  system store (`door_context()`, no CA parameter — D2772); three tasks per
  session (browser → door with the 64 KiB pending cap and `4400` for text;
  door → browser in ≤ 64 KiB binary frames with the 64 MiB cap; the idle/total
  timer); `max_queue=2`, `compression=None`, `server_header=None`, the library's
  loggers silenced; one line per session.
- **`services/sql-relay/Dockerfile`**: `PYTHON_BASE_IMAGE`, `WEBSOCKETS_VERSION`
  (no defaults), the install and a version self-check, uid 65532, `COPY
  relay.py` only, `EXPOSE 8080`, a `urllib` healthcheck, exec-form entrypoint.
  **Built once from the lock** (`~/s44/run2/image.txt`): 46.8 MB; with no
  environment exit 2 and *"refused to start: APG_SQL_RELAY_PORT is not set"*;
  read-only, `--cap-drop ALL`, uid 65532 → `healthy`; `websockets 17.1`, the
  system store present; a foreign `Origin` → `403` and one log line.
- **`tests/contract/test_sql_relay.py`** — 18 functions, 39 cases: every §2
  node id of `SQL-RELAY-001`–`003` plus `test_health_answers_without_an_origin`,
  `test_a_malformed_environment_refuses_to_start`, `test_a_text_frame_is_refused`.
  The relay served in-process before a fake door (asyncio, TLS from a CA made
  with `cryptography` in `tmp_path`); refusals read as raw status lines,
  sessions through the dev lock's `websockets` 17.1 sync client. **The canary**
  runs the relay as its own process, exactly as the image does, before
  PostgreSQL 18.4 from `POSTGRES_IMAGE` with TLS on: a SCRAM login with a known
  password and a statement carrying a marker — the marker came back (the
  control); not one byte of the password, the nonce, the proof, the
  server-first message, `SCRAM`, `SELECT`, the marker or the malformed second
  session's bytes in stdout or stderr; exactly two lines, each the ADR's shape.
  The timers' tests patch `IDLE_SECONDS`, `TOTAL_SECONDS`, `TICK_SECONDS`,
  `PING_SECONDS`, `CONNECT_SECONDS`, `MAX_DOWN_BYTES` by name.
- **Battery** (`~/s44/run2/battery2.py`, `battery2.txt`): the `Origin` check
  removed; `.search` for `.fullmatch`; the per-door ceiling +1; the idle timer
  never armed; `CERT_NONE` with no hostname check; the log line gaining a
  frame's first 32 bytes — **6/6 KILLED**, each by its named test(s) as
  `FAILED` (no `ERROR`), the control `test_the_grammar_agrees_with_naming`
  PASSED in the same invocation; restored, `cmp` identical; unmutated 21 passed.
- **Targeted, once:** `test_sql_relay`, `test_version_lock`,
  `test_repository_contract`, `test_environment_gates`, `test_acceptance_registry`
  (the sweep-selector guard), `test_compose_contract`,
  `test_operator_commands_run_on_the_host` — **443 passed**.
- Rows **D2771–D2773**. **CI on `8c1d1a8`: `contract` FAILED** (run 39659742863,
  `test_a_large_message_is_refused`, a race; D2776) — repaired test-only at `ef48bec`.

### Run 3 — the relay's plane (`compose.yaml`, `src/`, `bin/`, the edge labels)

**Read first:** D2733, D2739, D2740; `compose.yaml:1225-1275` (the console —
the service to copy); `runtime_override.py:264-265,673-674,723-724,1045-1058,1539-1558`;
`rendering.py:709-710,748-749,1016-1022,2253-2262`; `config.py:753-800`;
`naming.py:442-463`; `bin/deploy-project.py:460-470,2309,2497`;
`bin/project-runtime.sh:109-135`; `tests/contract/test_console_plane.py` whole;
`grep -rn "console_router_name\|APG_CONSOLE\b" src bin tests` (every reader of
the switch — D979).

1. **`naming.py`**: `sql_relay_zone(control_domain)`, `sql_relay_host(control_domain)`,
   `sql_relay_origin(host)` (`wss://…`), `SQL_RELAY_SERVICE = "sql-relay"`,
   `sql_relay_router_name(key)` (`traefik_name(f"apg-{key}-sql-relay", …)`),
   `SQL_RELAY_UPSTREAM` from `host_config.EDGE_PROXY_ALIAS` and the postgres
   entrypoint's port (`host_config.py:314-315`) — beside `console_origin`.
2. **`rendering.py`**: for the control project (the `control` switch, `:2253`)
   `APG_SQL_RELAY=1`, `APG_SQL_RELAY_HOST`, `APG_SQL_RELAY_ZONE`,
   `APG_SQL_RELAY_UPSTREAM`, `APG_CONSOLE_SQL_RELAY_ORIGIN`,
   `SQL_RELAY_ROUTER_NAME`; for every other project `APG_SQL_RELAY=0` and the
   others empty (the console's shape, D2691 — compose passes `${…?required}`,
   set possibly empty); `SQL_RELAY` in `SERVICE_RESOURCE_ORDER`; limits in
   `config.py` (**pids 64, cpus 0.5, memory 128 MiB** — Run 1's rig 44a peak
   under 32 sessions × 2 at least; if the peak exceeds 64 MiB, the limit is
   twice the peak rounded up to 32 MiB, and the row says so).
3. **`compose.yaml`**: `sql-relay:` after `console:` — `profiles: [sql-relay]`,
   build `./services/sql-relay` with `PYTHON_BASE_IMAGE` and `WEBSOCKETS_VERSION`
   args, `restart: "on-failure:5"`, the limits, `user: "65532:65532"`,
   `read_only: true`, `tmpfs: [/tmp]`, `cap_drop: [ALL]`, `no-new-privileges`,
   labels `apg.traefik.scope: managed` + `traefik.docker.network`, environment
   the four `APG_SQL_RELAY_*` names, the healthcheck, `networks: [edge]`; **no
   secret, no volume, no port, no `depends_on`**. The console's environment
   gains `APG_CONSOLE_SQL_RELAY_ORIGIN: ${APG_CONSOLE_SQL_RELAY_ORIGIN?required}`.
4. **`runtime_override.py`**: `build_override(…, sql_relay: bool,
   sql_relay_router_name)` (a relay without a router name raises — the
   console's rule); `_sql_relay_labels`: `traefik.enable`, rule
   ``Host(`${APG_SQL_RELAY_HOST:?required}`)``, entrypoint `websecure`,
   `tls.certresolver=${ACME_RESOLVER_NAME:?required}`, middlewares
   `${BASELINE_MIDDLEWARE_CHAIN:?required}` **only** (no buffering: rig 44a ran
   without it; no strip), service port 8080. `bin/deploy-project.py`
   `_override_sql_relay` beside `_override_console` and its two call sites.
5. **`bin/project-runtime.sh`**: `--profile sql-relay` iff `APG_SQL_RELAY=1`.
6. **The metrics filter** (`naming.project_router_names`, `:599-637`) — read
   whether the console's router is in it (it is not, §0); the relay's router
   follows the console's decision, recorded.
7. **Tests**: `tests/contract/test_sql_relay_plane.py` (§2's node ids; the
   render of `project.example.yaml` and of the control fixture) and
   `test_process_limits.py::test_the_sql_relay_is_bounded`;
   `bin/render-config.py --bounds-doc --write`; `test_console_plane.py`'s
   environment set (D2745) moves here **only if** compose's console environment
   moves in this run (it does: step 3) — under ADR 0285, named in the commit.
8. **The render without a host**: `--render-only` of the control fixture and of
   `project.example.yaml` as `op`, no root (CLAUDE.md §6); `.generated/<key>`
   removed after.
9. **Battery**: the profile added for every project; the rule widened to
   ``Host(…) || PathPrefix(`/`)``; a `secrets:` line on the service; the upstream
   typed instead of derived — each FAILED, the control passing, restored.

Targeted: `test_sql_relay_plane`, `test_console_plane`, `test_process_limits`,
`test_runtime_override*` (`grep -ln build_override tests/contract`),
`test_rendering*`, `test_container_selectors`, `test_environment_gates`, the
sweep-selector guard; `bin/session-01-check.sh` is NOT run (code run: CI).
Commit, push, read CI.

**Done.** (2026-10-21; WSL `~/s44/run3/`.)

- **`naming.py`**: `SQL_RELAY_SERVICE`, `sql_relay_zone` (refusing a zone of one
  label — D2775), `sql_relay_host`, `sql_relay_origin` (refusing a path or a
  port), `sql_relay_upstream(alias, port)` (the values passed in by the render,
  because `host_config` imports `config`, which imports `naming`), and
  `sql_relay_router_name`.
- **`config.py`**: `sql-relay` pids 64 / cpus 0.5 / memory 192 MiB (D2774, the
  real image's peaks: 40.49 MiB, 21 pids under 32 sessions).
- **`rendering.py`**: `SQL_RELAY` in `SERVICE_RESOURCE_ORDER`; nine keys in
  `COMPOSE_ENV_KEYS` (`SQL_RELAY_MEMORY_LIMIT`, `SQL_RELAY_ROUTER_NAME`,
  `APG_SQL_RELAY`, `APG_SQL_RELAY_HOST`, `APG_SQL_RELAY_ZONE`,
  `APG_SQL_RELAY_UPSTREAM`, `APG_CONSOLE_SQL_RELAY_ORIGIN`, and the pids/cpus
  pair from the order); control: `1`, `sql.<zone>`, `<zone>`,
  `apg-edge-proxy:8432` (from `host_config`), `wss://sql.<zone>`; elsewhere `0`
  and empty.
- **`compose.yaml`**: `sql-relay` after `console` — profile `sql-relay`, built
  from `services/sql-relay` with `PYTHON_BASE_IMAGE` and `WEBSOCKETS_VERSION`,
  the limits, uid 65532, read-only, `/tmp` tmpfs, every capability dropped,
  `no-new-privileges`, the four environment names (the allowed origin IS
  `APG_CONSOLE_ORIGIN`), the healthcheck, network `edge`; no secret, volume,
  port or `depends_on`. The console's environment gains
  `APG_CONSOLE_SQL_RELAY_ORIGIN` (its server reads it from Run 5).
- **`runtime_override.py`**: `build_override(…, sql_relay, sql_relay_router_name)`
  (a relay without a name raises), `_sql_relay_labels` — rule
  ``Host(`${APG_SQL_RELAY_HOST:?required}`)``, `websecure`, the resolver, the
  baseline chain only, port 8080; `bin/deploy-project.py` `_override_sql_relay`
  at both call sites; `bin/project-runtime.sh` `--profile sql-relay` iff
  `APG_SQL_RELAY=1`.
- **The metrics filter** (`naming.project_router_names`): the console's router is
  not enumerated, so the relay's is not either (the console's decision followed).
- **Tests**: `tests/contract/test_sql_relay_plane.py` (five: the profile, the
  rule, nothing held, the names derived, the upstream following the edge's
  constants) and `test_process_limits.py::test_the_sql_relay_is_bounded`;
  fixtures moved under ADR 0286: the service counts (23 → 24, long-running
  12 → 13), the cpus exceptions and the memory set (`test_process_limits`),
  `BUILT_SERVICE_USERS` (`test_compose_contract`), the console's environment
  (three names, `test_console_plane`), the control example's domain (D2775).
- **The render without a host** (`~/s44/run3/render.txt`, uid 1000):
  `--render-only` of the control example and `project.example.yaml` rc 0; the
  control render's model resolves under `--profile sql-relay --profile console`
  with every value rendered (`compose-config.txt`); `.generated/fixture-control-dev`
  removed; `render-config --bounds-doc` already current.
- **Battery** (`battery3.py`): the profile for every project; the rule widened
  with ``|| PathPrefix(`/`)``; a `secrets:` line; the upstream typed — **4/4
  KILLED** as `FAILED`, the control `test_the_sql_relay_is_bounded` PASSED,
  four files restored, `cmp` identical. (A typed value EQUAL to the derived one
  is invisible to any reading of the output — D493 — so the test that kills it
  moves the edge's constants and watches the render follow.)
- **Targeted, once** (three foreground shards — the plan's list plus every
  module that renders the control example): shard A 983 passed and the canary failing on its flaky expectation, repaired (D2776) and re-run green three times with its module 39/39; shard B (every test_control_* module) 135 passed; shard C 192 passed.
- Rows **D2774–D2776**. CI on `b90e3fc`: read after its push (queued behind
  `ef48bec`), recorded in Run 5.

### Run 4 — the wire client (`services/console/public/pg.js`, tests)

**Read first:** D2732, D2735, D2754, D2755; rig 44b's prototype and readings;
`services/console/public/scram.js` whole (the WebCrypto primitives to reuse —
`pg.js` imports from it rather than repeating them); PostgreSQL's protocol
documentation chapters *Message Flow* and *Message Formats* and *SASL
Authentication* (read for the 18 message types used, cited by section in the
file's header); `tests/contract/test_console_scram.py` (how a console script is
run in Node).

1. **`pg.js`** (an ES module, no global state, no DOM): `connect({relay, host,
   user, database, password})` → a connection object with `query(text)` (an
   async iterator of results: `{columns, rows, command, notices}` or a thrown
   `PgError {code, message, detail, hint, position}`), `cancel()`, `close()`,
   the caps (1,000 rows / 2 MiB → a cancel and a `truncated` flag), the 60 s
   deadline (D2735); `password` read once into the SCRAM closure and dropped
   after `AuthenticationOk`. **Every parse bounded**: a message length over 1 MiB
   or under 4 closes the connection with a named error.
2. **Tests** `tests/contract/test_console_pg.py` (`pytestmark` first; Docker-backed
   for the database ones): pure Node tests of the message bytes and the SCRAM
   proof against Python's (fixed nonce and salt passed by a test-only hook the
   page never calls — **a guard that `app.js` never passes it**); a PostgreSQL
   18.4 + PgBouncer (both pool modes) + the in-process relay from Run 2 for the
   rest — every §2 node id of `SQL-CLIENT-001`.
3. **Battery**: the server-signature check skipped; `MD5` accepted; the row cap
   off-by-one; the cancel sent on the same socket; the length bound removed — each
   FAILED, the control passing, restored.

Targeted: `test_console_pg`, `test_console_scram`, `test_console_pages` (the
guards over `public/*.js` now read `pg.js`), `test_console_server` (`pg.js` is
not yet a ROUTE: **the file lands in `public/` with its route in this run**, so
`LISTED` and `ROUTES` gain `/console/pg.js` here, D2745). Commit, push, read CI.

**Done.** (2026-10-22; WSL `~/s44/run4/`.)

- **`services/console/public/pg.js`** (ES module, no DOM, no global state): the
  startup message (protocol 3.0; `user`, `database`, `application_name =
  apg-console-editor`); SASL SCRAM-SHA-256 only — `clientFinal` refuses a
  server-first message whose nonce does not extend the client's or whose
  iteration count is below 4,096 (D2767), and the server's signature is checked
  before `AuthenticationOk` is accepted; the simple query protocol as an async
  iterator of results `{columns, rows, command, notices, truncated}`, an
  `ErrorResponse` thrown as `PgError {code, message, detail, hint, position}`
  after the results before it and once the server is ready; `CopyFail` for COPY
  in, COPY out dropped with a notice, `CopyBothResponse` closes; the caps (1,000
  rows / 2 MiB → one cancel, `truncated`, the cap's own `57014` swallowed —
  D2766); the 60 s deadline (`deadlineSeconds`, its `57014` thrown with
  `deadline: true`); a cancel as its own relay session, one at a time, and the
  next statement waiting for it; every message bounded (under 4 bytes or over
  1 MiB closes with a named error); the password read only inside
  `authenticate`. The header cites the protocol chapter's sections.
- **`scram.js`** exports `base64`, `hmac`, `scramKeys` (D2780). **`serve.py`**
  routes `/console/pg.js`; `test_console_server`'s `LISTED` and
  `test_console_scram`'s names (`api`, `app`, `pg`, `scram`) moved with it.
- **`tests/contract/test_console_pg.py`** — 19 cases, every §2 node id of
  `SQL-CLIENT-001` plus `test_a_message_outside_the_bound_closes_the_connection`.
  Pure (9): the startup and cancel bytes against Python's; `clientFinal` equal to
  Python's for two exchanges and refusing three; a fake SCRAM server forging its
  signature (the control: signing correctly → connected, pid 7 key 42); MD5,
  cleartext, trust, `SCRAM-SHA-256-PLUS` alone and a stray `ReadyForQuery` each
  refused with nothing sent after; a length over and under the bound. **Live
  (10), first execution green**: PostgreSQL 18.4, PgBouncer 1.24.1 in
  transaction and session mode with client TLS (D2781), the relay in this
  process (D2778), Node's `WebSocket` given the console's `Origin` (D2777) —
  rows and NULLs and tags; `22012`, `42601` at position 1, `42501`, the
  connection usable after; a wrong password `08P01` (D2765); COPY both ways;
  a cancel `57014` in under 6 s and its session closed, the uncancelled
  control completing, the 2 s deadline flagged; the fast, live and byte caps
  `truncated` at 1,000 / 1,000 / ~511 rows with no error and the next statement
  answered; the role's connections within its limit 2.
- **Battery** (`battery4.py`): the signature check skipped; MD5 accepted; the row
  cap off by one; the cancel sent on the same socket; the length bound removed —
  **5/5 KILLED** in round 2, each `FAILED` (no `ERROR`), the control
  `test_the_startup_message_is_exact` PASSED, `cmp` identical, the unmutated
  module 19 passed (round 1 left the cancel mutation as `ERROR`, D2782).
- **Targeted, once:** `test_console_pg`, `test_console_scram`, `test_console_pages`,
  `test_console_server`, `test_acceptance_registry` (the sweep-selector guard),
  `test_environment_gates` — 73 passed.
- Rows **D2777–D2782**.

### Run 5 — the editor page, the policy, the Ledger exception (`services/console/`, `docs/`)

**Read first:** D2733–D2738, D2744–D2746, D2755–D2757; ADR 0285;
`services/console/public/app.js` whole; `public/pages.json` whole;
`tests/contract/test_console_pages.py`, `test_console_server.py`,
`test_reality_ledger.py:251-280` whole; rig 44e's recorded module boundary.

1. **`serve.py`**: `policy(relay_origin)` (D2744), read once at start from
   `APG_CONSOLE_SQL_RELAY_ORIGIN` (refuse to start unless `wss://<host>` alone);
   `env.json` gains `"sql_relay"`.
2. **`public/sql.js`** (DOM-free decisions, rig 44e) and the view in `app.js`:
   `#/projects/{key}/sql` — reads the project (`state`, D2737) and its
   connections (D2738); the door chooser (pooled as `customer_app`, direct as
   `customer_admin`, from the answer); the password field (D2756); **Connect**,
   **Run**, **Cancel**, **Disconnect**; results as text-node tables; every
   refusal and close code a sentence (`4502` *"The database could not be
   reached."*, `4429` *"Too many editor sessions are open; try again in a
   minute."*, `4408` *"The session ended after 30 minutes or 5 idle
   minutes."*, `4413`, `1009`, PostgreSQL's own message for an `ErrorResponse`);
   the 60 s sentence. `projectNav` gains *"SQL"*; `connectView` gains the link.
3. **`pages.json`**: view `sql-editor`, ledger `["sql_editor", "pooled_endpoint",
   "direct_endpoint"]`, calls `GET /projects/{key}`, `GET
   /projects/{key}/connections`. **The Ledger guard's exception** for
   `sql_editor` (one id, a comment naming D2746 and *"removed by Run 7"*).
   ROUTES gain `/console/sql.js`; `test_console_scram`'s names gain `sql`.
4. **The documents**: `docs/product-contract.md:631-633` (ADR 0285's words);
   `docs/decisions/0246-…md` status line (*Amended by ADR 0285*);
   `docs/control-plane.md`'s console paragraph (one sentence: the editor, the
   relay's name). **The site page waits for Run 7** (the row is not reachable
   yet).
5. **Tests**: every §2 node id of `SQL-PAGE-001`; the D2745 moves
   (`test_console_server.py`'s `POLICY` and `LISTED`; `test_console_plane.py`
   already moved in Run 3).
6. **Battery**: `connect-src` gaining `wss:` (any host); `sql.js` opening the
   socket while `sleeping`; the password written to `sessionStorage`; a second
   file calling `new WebSocket`; a cell rendered by `innerHTML` — each FAILED,
   the control passing, restored.

Targeted: `test_console_server`, `test_console_pages`, `test_console_sql`,
`test_console_scram`, `test_console_plane`, `test_reality_ledger`,
`test_documentation_index`, `test_session12_documented_path`, the Session 43
external module's `--collect-only` (it reads the policy from `serve.py` — its
helper must still load). Commit, push, read CI.

**Done.** (2026-10-22; WSL `~/s44/run5/`.)

- **`serve.py`**: ADR 0280's directives with `connect-src 'self' {relay}`;
  `policy()` and `security_headers()` refusing anything but `wss://<host>`;
  read once at start from `APG_CONSOLE_SQL_RELAY_ORIGIN`, `main` exiting 2 on a
  bad value (D2783); `env.json` answers `{"api", "sql_relay"}`; `/console/sql.js`
  routed.
- **`public/sql.js`** (DOM-free, imports nothing — rig 44e): `stateSentence`
  (asleep / named / could-not-be-read — D2737, D2768), `doors` (from the
  connections answer; `409 not_available` → not offered — D2738), `openDoor`
  (the state first, then — only if it may — the password, then `connect`),
  `endSentence` (every close code and `08P01`/`28P01` a sentence, never
  *asleep*), `runStatement` (results as plain values, the cap's sentence, the
  deadline's). **`api.js`** exports `relayOrigin()` (D2784).
- **`app.js`**: `#/projects/{key}/sql` — the door chooser from the answer, one
  `type=password autocomplete=off` input cleared the moment it is read, Connect /
  Disconnect / Run / Cancel, results as text-node tables (`NULL` shown as text),
  the 60 s sentence; the session closed on every navigation and on `pagehide`;
  *SQL* in the project's tabs; *Open the SQL editor* on the Connect page.
  **The view's DOM half is executed first by Run 6's offline rehearsal** (its
  decisions are executed here, in Node).
- **`pages.json`**: view `sql-editor`, rows `sql_editor`, `pooled_endpoint`,
  `direct_endpoint`, calls `GET /v1/projects/{key}` and `…/connections`; the
  one-id exception in both page guards (D2785).
- **Documents**: `product-contract.md`'s boundary sentence in ADR 0285's words;
  `control-plane.md`'s console paragraph names the editor and the relay's name.
- **Tests**: `test_console_server.py` — `POLICY` is now the exact string for the
  fixture relay, `test_the_policy_admits_the_relay_alone` (one directive moved,
  by one origin), `test_a_bad_relay_origin_refuses_to_start` (eleven origins,
  each refused by `policy()` and by the process); `test_console_pages.py::
  test_only_pg_js_opens_a_websocket`; `tests/contract/test_console_sql.py` (four:
  every `control_states.STATES` value plus an unreadable state — a socket for
  `ready`/`updating` only; no doors → no editor and another refusal re-raised;
  the password only in `connect`'s arguments and no page deadline of its own;
  every ending a sentence); the names and routes lists gain `sql`.
- **Battery** (`battery5.py`): `connect-src` gaining `wss:`; `sql.js` opening
  while `sleeping`; the password written to `sessionStorage`; a second file
  calling `new WebSocket`; a cell by `innerHTML` — **5/5 KILLED** as `FAILED`,
  the control `test_the_log_names_no_query` PASSED, three files restored, `cmp`
  identical.
- **Targeted, once:** the console's six modules, `test_reality_ledger`,
  `test_site`, `test_documentation_index`, `test_session12_documented_path`,
  `test_acceptance_registry`, `test_environment_gates`, `test_console_pg` — **184
  passed**; `tests/external/test_session43_console.py --collect-only` collects 12.
- Rows **D2783–D2785**.

### Run 6 — the trip's instruments, written and rehearsed offline

**Read first:** D2748–D2750, D2757, D2758; Session 43's Run 8 text and its
`**Done.**` (`docs/plans/session-43-implementation-plan.md:1605-1741`) and rows
D2713–D2716; `tests/external/browser/console_walk.py` whole;
`tests/external/test_session43_console.py` whole; `~/s43/run8/` (every
instrument) and `~/s43/run10/NOTES.md`.

1. **The editor driver** `tests/external/browser/sql_walk.py` (the console
   walk's shape, D2758): sign in as the probe owner; open `slot3-prod`'s editor;
   read the state; **pooled door** (`customer_app`, the password from the creds
   file): `SELECT current_user, current_database()`, the marker statement
   (D2743), `SELECT count(*) FROM pg_stat_activity WHERE usename =
   current_user` (D2736), `SELECT * FROM app_private.migration_ledger LIMIT 1`
   → the error's code (`42501` or `3F000` — **whatever PostgreSQL answers is
   recorded, and the proof asserts it is a refusal by PostgreSQL**, never a
   literal guessed here), `SELECT pg_sleep(30)` cancelled by the button
   (`57014`), `SELECT generate_series(1, 5000)` (capped), 20 × `SELECT 1` timed;
   **direct door** (`customer_admin`): `SELECT current_user`, the count; the
   relay's refusals through `context.request`-free raw clients (a foreign
   `Origin`, a name outside the grammar, `pool.slot99.<zone>`); disconnect; sign
   out. **One record** (JSON, 0600; each step's name, outcome, times, the codes,
   the counts, the marker, Chromium's version; **no secret value** — `self_check`
   exits 6 if any held secret appears). A `--rehearse` mode answering from
   fixtures (the console walk's).
2. **The trip scripts** in `~/s44/run6/`, derived from `~/s43/run8/` by named
   substitution and read whole after: `s44-window.py`, `s44-after.sh` (+ the
   relay container and `https://sql.agenticpostgresql.com/__apg/healthz` for
   R2d), `s44-walk.py/.sh` (W0′/W1′, D2749), `s44-sql.sh` (E0/E1: the pinned
   Playwright image, the checkout mounted read-only, `--network host`; then
   `psql` timing from the workstation, D2750), `s44-lifecycle.py`,
   `s44-branches.py`, `s44-hostyaml.py` (**its comment text moved, D2727**),
   `s44-dns.sh`, `s44-r2shape.py`, `s44-sweep.sh`, `s44-external.sh` (with
   `--console-record-file` W1′'s and `--sql-editor-record-file`).
3. **The host module** `tests/deployment/test_session44_sql_relay_host.py`
   (§2's `SQL-HOST-001`; the log read by `docker logs` as root in the sweep;
   the marker from the record via an existing host gate or a new one — **read
   the roster first; a new host gate is a row**).
4. **The widening** (D2748, D2749): every record-reading module's `session`
   tuple gains 44 (`grep -rn "\"session\")\|get(\"session\")" tests/external
   tests/deployment` — the list recorded; each edit anchor-checked once, a miss
   fatal, `/tmp/s44-widen.py`); **no `source_commit` check touched**.
5. **The external module** `tests/external/test_session44_sql_editor.py` and its
   roster entry are **PARKED** in `~/s44/run6/park/` (D2715) — they land in Run 7
   with the gate.
6. **Rehearsed offline**: the editor driver `--rehearse` in the Playwright
   image (every step ok, `self_check` clean); `pytest --setup-plan` of the host
   module with the variables set (D671).

Targeted: `test_session44_sql_relay_host --collect-only`,
`test_environment_gates`, the sweep-selector guard, the widened modules'
`--collect-only`. Commit (the driver, the host module, the widening), push,
read CI.

**Done.** (2026-10-22; WSL `~/s44/run6/`.)

- **The editor driver** `tests/external/browser/sql_walk.py` (the console walk's
  shape; D2758): signs in as the probe owner with TOTP; reads the relay's origin
  from `env.json`; opens `slot3-prod`'s editor recording the connections answer;
  on the pooled door who-am-I, the marker statement, the role's connections,
  `app_private` (the code PostgreSQL gives), Cancel on `pg_sleep(30)`, 5,000 rows
  capped, 20 timed `SELECT 1`; on the direct door who-am-I and the count; the
  relay's three refusals by raw TLS clients (live only); sign out. One 0600
  record, the secrets held only for `self_check` (exit 6). `--rehearse` (D2789),
  `--leak`, `--dry` (E0).
- **Rehearsed offline** (`~/s44/run6/rehearse-sql.sh`, the console image built
  from the tree on `127.0.0.1:18081`): **every step ok**, exit 0, 17.2 s —
  `apg_slot3_prod_customer_app`/`slot3_prod`, `42501`, the cancel `57014` in
  1.10 s, 1,000 rows `truncated`, the editor's `SELECT 1` median 62.5 ms against
  the fake, the password field cleared both times, the policy served
  `connect-src 'self' wss://sql.rehearsal.test`; **`--leak` → exit 6, no record
  written**; `--dry` → exit 0. The editor's DOM ran in Chromium for the first
  time here.
- **The trip scripts** (`~/s44/run6/`): nineteen derived by `s44-derive.py` (58
  named substitutions, `derive-counts.txt`; the diffs read, `derive-diffs.txt`;
  D2790) and `s44-post-derive.py`'s hand edits — the sweep's summary names
  `sql_relay_host`, the external half passes `--sql-editor-record-file
  ~/s44/sql/record.json`, X0 skips `session44_sql`, `s44-after.sh` reads the
  relay at R2d (health, certificate, a foreign `Origin`, the console's
  `connect-src`). New: **`s44-sql.sh`** (E0/E1, then the `psql` timing — D2788).
  `bash -n` and `shellcheck -S warning` clean on all. `s44-walk.py --check`:
  preconditions refused before the deploy as designed (exit 92), the image and
  the Playwright package hold (`~/s44/walk-home/pw`).
- **The host module** `test_session44_sql_relay_host.py` (four proofs; the log by
  D2786; `memory.peak` recorded as a JUnit property; `Mounts == []` and
  `Tmpfs == {"/tmp"}`, the latter measured on a compose service first) —
  `--setup-plan` with every variable set and `--collect-only` clean, then
  **PARKED** with the external module `test_session44_sql_editor.py` (thirteen
  proofs, SQL-LIVE-001/002) in `~/s44/run6/park/` (D2787, D2715).
- **The widening** (D2748, D2749; `widen.py`, every anchor once): ten
  record-reading modules accept 44 — Sessions 38–43's lifecycle, branch and
  console proofs, external and host; **no `source_commit` check touched**.
- **Targeted, once:** `test_deployment_suite_shape`, `test_environment_gates`,
  `test_acceptance_registry` (the sweep-selector guard), `test_repository_contract`
  — 279 passed; the ten widened modules collect (89).
- Rows **D2786–D2790**.

### Run 7 — the bump, the registry, the gate, the threat rows, the Ledger to `trial`

**Read first:** §2 whole; `src/agentic_postgres/__init__.py:1271-1340`;
Session 43's Run 9 (`docs/plans/session-43-implementation-plan.md:1742-1836`) —
the list to copy; `bin/upgrade.py --also` and `src/agentic_postgres/compatibility.py`
(what a new compose service under a profile, a changed console environment and
a changed image declare); `bin/session-43-check.sh:1-230`;
`tests/contract/test_session_forty_three_gate_modes.py:40-120`.

1. **The constant and the version**: `CURRENT_SESSION = 44` with Session 44's
   paragraph (the D690 shape of `:1271-1334`); `VERSION` `1.22.0`;
   `README.md:7`; every `--session 43`/`--through-session 43` literal on the
   documented path moved and counted per file (D678/D1484); the operator and
   upgrade guides' release lines and the upgrade table's 1.22.0 row (*"restarts
   every project's database once — a new Postgres image"*, D2747).
2. **The registry**: §2's nine requirements under `# Session 44 (ADR
   0285-0286)` after `:8300`, node ids from `pytest --collect-only -q`; the regex
   gains `SQL`; `CLAIMS` and `OFFLINE_CLAIMS` blocks; `CLAIM_INTRODUCED_IN`;
   `APG_SQL_EDITOR_RECORD_FILE` in the roster; **the parked external module
   unparked** (D2715).
3. **The gate**: `bin/session-44-check.sh` from 43's by `sed` of the session
   numbers into a copy, then the header and usage block rewritten whole (D1488),
   then `--sql-editor-record-file` added (D2752) — **`diff bin/session-43-check.sh
   bin/session-44-check.sh` read whole before the commit; every hunk named in
   the `**Done.**`**. `SHELL_COMMANDS` gains it after `:269`;
   `test_session_forty_four_gate_modes.py` from 43's by the same method, its
   claims the nine, plus `test_the_gate_exports_the_sql_editor_record_in_the_external_mode_alone`.
4. **The Ledger** (D2746): `sql_editor` → `trial`; the guard's exception
   removed; the `console` row's sentences; the `no data view` sentences re-read
   (each decision listed); `test_site.py:165`'s fixture → `passkeys`;
   `site/pages/docs/sql-editor.md` (what it is, the two doors, the password is
   yours and stays in the page, the 60 s cancel and the 30 min session, *"the
   relay carries your session and records none of it"*, what is not offered:
   branches' doors, saved statements, export); `bin/render-reality-ledger.py
   --write`.
5. **The threat rows**: items 22–26 into the table as `THR-SQL-*` with their
   requirements (D2753).
6. **The derived documents** (CLAUDE.md §5's list): `render-acceptance-matrix.py
   --write`, `render-config.py --bounds-doc --write`, `bin/app-contract.sh
   --check`, `bin/mcp-contract.sh check`, `bin/apg.sh generate --check --project
   project.example.yaml`, `render-mcp-catalog.py --write`,
   `render-evaluation-report.py --write`.
7. **Battery** (`battery7.py`): the gate's literal; the record's export; the row
   left `planned`; `SQL` out of the regex; a threat row's missing test; an
   offline claim undeclared; a host node id renamed; the roster entry dropped —
   each FAILED, the control passing, restored.
8. **The gates, in shards, once** (D2554; `~/s44/run7/` from `~/s43/run9/`'s
   `gate01-*.sh` and `gate43-*.sh` by diff; `TMPDIR=~/s44/tmp`; each shard under
   `timeout 570` in the foreground; the JUnit merged; the total checked against
   the collected count): `bin/session-01-check.sh` and `bin/session-44-check.sh
   --mode offline`. Commit **before** the gates (they refuse a dirty tree), then
   push after both pass. Read CI. Then a documentation commit recording the
   gates (no CI read).

**Done.** (2026-10-22; WSL `~/s44/run7/`.)

- **The constant and the version** (`bump44.py`, `session-paragraph.py`):
  `CURRENT_SESSION = 44` with its paragraph in the D690 shape (the claims counted
  from the tuples, the subject, the schemas, the price); `VERSION` 1.22.0;
  `README.md`; the documented path's thirteen `--session 43` literals moved; the
  operator and upgrade guides' release lines and the upgrade table's 1.22.0 row
  (`docs44.py`: every database restarts once, the control project's deploy starts
  one container, no migration, proposed as a minor — D2791).
- **The price** (`upgrade44.sh`, `upgrade.txt`; D1624's rig against the deployed
  `012ac06`): `bump minor`, `requires patch`, verdict `ok`, `changes
  [image_digest]`, two leaves (`versions_lock_sha256`, `template_version`) —
  **1.22.0 kept above the floor** (D2791).
- **The registry** (`registry44.py`, `claims44.py`): nine requirements —
  `SQL-CLIENT-001`, `SQL-RELAY-001..003`, `SQL-PLANE-001`, `SQL-PAGE-001`,
  `SQL-HOST-001`, `SQL-LIVE-001..002` — node ids from `--collect-only`; the
  regex gains `SQL`; **424 requirements; `CLAIMS` 331, `OFFLINE_CLAIMS` 155**;
  `CLAIM_INTRODUCED_IN` at 44; `APG_SQL_EDITOR_RECORD_FILE` in the roster; the
  host and external modules unparked (D2787, D2715).
- **The gate** (`derive44.py`, `make-gates44.sh`): `bin/session-44-check.sh` from
  43's by `sed`, its header and usage block rewritten whole, then the one flag.
  **The diff read whole — 33 hunks**: the header (the subject, the six offline /
  two external / one host claims, the sweep's declarations with `slot8-prod`);
  `SESSION=44` and `SQL_EDITOR_RECORD_FILE=""`; the usage block's three modes
  rewritten (Session 43's text kept below each, its claims inherited); the flag's
  help, its two parse arms and its `=` refusal; its existence check and the
  export; the session number in the inherited prose (*"Sessions 36 to 44"*).
  `SHELL_COMMANDS` gains it; `test_session_forty_four_gate_modes.py` from 43's
  plus `test_the_gate_exports_the_sql_editor_record_in_the_external_mode_alone`.
- **The Ledger** (`ledger44.py`, `unexcept.py`, `site-fixture.py`): `sql_editor`
  → `trial` on its three live claims; the `console` row's two sentences the
  editor made false; the four agent rows' *"no data view"* re-read and kept; both page guards' one-id exception removed;
  `test_site.py`'s fixture → `passkeys`; `site/pages/docs/sql-editor.md`
  (naming no host — D2792).
- **The threat rows** (`threats44.py`): items 22–26 as `THR-SQL-PROXY`,
  `-SECRET`, `-EXHAUST`, `-READ`, `-DEADLINE`, each with its requirements.
- **The derived documents** (`regen.sh`): the matrix (424), bounds, the reviewed
  surfaces, the client (`contract.ts`'s version line), the catalog, the
  evaluation report — all current at the gate's steps 6–7.
- **Battery** (`battery7.py`): **8/8 killed**, each `FAILED` with its control
  green, restored by copy and `cmp` — the gate's literal; the record's export;
  the row left `planned`; `SQL` out of the regex; a threat row's test missing; an
  offline claim undeclared; a host node id renamed; the roster entry dropped
  (first run named the wrong test and SURVIVED — the reader broken, not the guard;
  re-run on `test_every_gate_names_a_registered_variable`, killed).
- **Targeted, once**: 1,389 passed, 1 failed (`test_site`'s host guard — D2792,
  repaired before the commit `df5ff04`).
- **The gates, in shards** (D2554; `TMPDIR=~/s44/tmp`, each shard `timeout 570`
  in the foreground): **`bin/session-01-check.sh` PASSED** — steps 1–3, 5–7 at
  `df5ff04`; shards 1–3 at `df5ff04`, 4–6 at `6f90455` (D2793), 7 at `6f90455`,
  10 and 11 at `c947180`, 8 and 9
  re-run at `c947180` (D2794; first attempts kept); step 8 merged **8,362 =
  collected, 0 failed, 3 skipped**, evidence written. **`bin/session-44-check.sh
  --mode offline` PASSED at `c947180`** on a clean tree: steps A (1, 2, 2b, 4–7),
  eleven shards **8,371 = collected, 0 failed, 3 skipped**, step B (8, 8b, 8c),
  step 9 — `evidence/session-44-offline.json`, checkout `c947180`, **155 of 155
  claims passed**.
- **Pushed**: `0a77af9` (Run 5) CI green (contract 39678381757, site
  39681875750); `6fd2313` (Run 6) alone, green (contract 39737460801);
  `df5ff04` + `6f90455` + `c947180` together, **green on the head** (contract
  39740975116).
- Rows **D2791–D2794**. **NEXT FREE D2795, ADR 0287.**

### Run 8 — the sitting: the release, the walks, the re-earning, the sweep, the tag, the publish

**Read first:** this plan's appendix (every sheet) and §7; Session 43's Run 10
(`:1838-1968`) and rows D2725–D2729 (*what went wrong*, D977); `~/s43/run10/NOTES.md`.
**Before the first sheet**: the checkout on the host moved to the Run 7 commit
by bundle (`git bundle` + `scp` to `/tmp/apg-<sha>.bundle`, `git fetch`, `git
rev-parse FETCH_HEAD` confirmed, `git checkout`), `uv sync`, the renders of the
four projects (`--render-only` as `op`), `pytest --setup-plan` of the host
modules with the variables set; **`nslookup sql.agenticpostgresql.com`** →
`15.204.231.45` (D0 still in place); the Playwright image present.

1. **R1** (price; with `--also` as D2726 needs — expected `image_digest` and the
   console's environment) → **R2a** beta-dev, **R2b** alpha-dev, **R2c**
   `slot3-prod` by `slot.sh redeploy`, **R2d** control-prod — each with
   `s44-window.py`, each read by `s44-after.sh` before the next sheet (D1510);
   **each sheet says the database restarts**. After R2d: the relay container
   healthy; `curl -sI https://sql.agenticpostgresql.com/__apg/healthz` → 200
   with a Let's Encrypt certificate naming the host (**read once; if the
   certificate is not there within 5 minutes, §9's stop — never a re-deploy to
   retry ACME**); `https://control.agenticpostgresql.com/console/` → 200 with
   the policy naming the relay.
2. **A1**, **RA** (after the last deploy, D2494), **K1**.
3. **V1** (the host suite writing nothing), **X0** (the external suite, the
   Session 44 module excluded, writing nothing), **W0′** (`s44-walk.sh --dry`),
   **E0** (`s44-sql.sh --dry`: sign-in, the editor, one `SELECT 1` on each door,
   the relay's refusals — no record kept). **If any fails: repair, move the
   commit, redeploy all four.**
4. **W1′** — the console walk (D2749; the creds file replaced). **E1** — the
   editor walk (D2758; reads W1′'s password; the record; the `psql` timing).
5. **The re-earning** (D2748) — Session 43 Run 10 step 4b, `slot7` → `slot8`,
   every script `~/s44/run6/s44-*`: **H1**, **SL1**, **SL1b**, **SL2**, **SL3**,
   **RC1**, the lifecycle (`lifecycle-s44`, **K2** at its pause), the branches on
   `slot3-prod` (`s44-branches.py`, after E1), **A1′**, **B1** (the reboot;
   `s44-after-reboot.sh` BEFORE any sweep; then `s44-branches.py
   --after-reboot`; **then the relay read healthy again by itself**).
6. **S1** — the one sweep (host evidence with the live slot's outputs, K2's
   copy, the Session 44 records); **then the branch `--delete-only`** (D2647);
   **then the external half** from WSL (`s44-external.sh` with both record
   files — `site_live` re-earned here, D2728); then **the merge** (`write-session-evidence`
   with the CI artifact's offline half for the deployed SHA). **Exit 5 for
   `documented_path` only** (§7).
7. **The tag** from the workstation (D2041): `git tag -a 1.22.0 <sha> -F msg.txt`,
   `git push origin 1.22.0`; the `publish-cli` run read (`verify`, `build`,
   `publish` green); PyPI `agentic-postgres-cli` `info.version` `1.22.0`;
   installed in a clean `python:3.12-slim` (`apg --version` → `apg 1.22.0`).
8. **SL4** — `slot8-prod`'s identity revoked after the tag; **RC1** — the
   reconciler started and read active after the last sheet that stopped it
   (D2178).

**Done.** (2026-10-22 13:0xZ – 2026-10-23 07:09Z, host clock; WSL `~/s44/run8/`,
minute by minute in `NOTES.md`.)

- **Before the first sheet**: `4b6c024` by bundle, `FETCH_HEAD` confirmed, no
  dependency file moved; five renders (control-prod `APG_SQL_RELAY=1`, host
  `sql.agenticpostgresql.com`); the host module's `--setup-plan` exit 0;
  `nslookup sql` → `15.204.231.45`; the Playwright image present.
- **R1**: `bump minor`, `requires patch`, `changes [image_digest]` on alpha, beta
  and control — no `--also` (no migration, no API operation; D2791).
  **R2a–d at `4b6c024`**, each database restarted once (D2731's image): rest down
  4.7 / 4.4 / 4.0 s, auth 9.7 / 8.5 / 9.0 / 9.5 s (beta, alpha, slot3, control).
  After R2d the relay first answered `/__apg/healthz` 200 at 13:24:53Z with a
  Let's Encrypt certificate (YR1, CN/SAN `sql.agenticpostgresql.com`); a foreign
  Origin's upgrade 403; the console 200 with `connect-src 'self'
  wss://sql.agenticpostgresql.com`; listeners 22/80/443/5432 only.
- **RC1, A1, RA, K1** (`kit-2026-10-22-s44`); **V1** 411 passed, 2 failed —
  `documented_path` and the relay-log proof's control (no walk yet; D2800);
  **X0** 40/0; **W0′** 9/9 (31.9 s).
- **E0 failed at `4b6c024`** — D2795: `slot3-prod` read `unknown`.
  **ADR 0287** fixed at `224b660` (CI contract 39801089169, site 39805265547 green),
  **R3a–d at `224b660`**, no database restart: auth down 9.7 / 6.9 / 9.0 s, rest and
  the console never; the relay untouched. RC1/A1/RA/K1 again (`kit-2026-10-22-s44b`),
  X0 40/0, W0′ 9/9, **E0 EXIT 0** (pooled 1.71 s, direct 1.97 s, the refusals).
- **W1′**: `customer_app` rotated from the Connect page, link → connection string
  28.4 s, FCP 1,016–1,084 ms, the creds replaced (`.before-s44` kept); `slot3-prod`
  still `ready`. **E1** (attempt 1 lost to the executor's TOTP replay, D2802):
  EXIT 0 in 42 s — sign-in 6.64 s; pooled connect 1.55 s, direct 1.59 s;
  `app_private` 42501; `pg_sleep(30)` cancelled 57014 in 2.03 s; 5,000 rows capped
  to the page; 20 × `SELECT 1` median **295.0 ms** in the editor against **197.3 ms**
  from `psql` on the same workstation (D2750); refusals 403 / 400 / 4502; the
  password field cleared. Record `~/s44/sql/record.json`.
- **slot8-prod** (D2748): H1 (both copies, `dc34b173`); DNS × 3 grey and R2 × 2
  EEUR by the agent through the Cloudflare API; the operator's providers and
  Infisical; SL1b ALL YES, SL2 29 files, SL3 ready, RC1. **The lifecycle** took four
  attempts (D2796, D2797): create **1,479.5 s**; wake first answer **17.2 s**; resizes
  304 / 840 admitted of 4,801 safe; export 40,286 B, `pg_restore` 0; the idle sleep
  requested **1,189.2 s** after the setting; deleted; the second creation refused
  `no_slot`. K2 run early by mistake, harmlessly (D2803). The neighbours lost
  nothing (8,452 s, 0 down; control 13,521 up).
- **The branches** on `slot3-prod` (detached, exit 0): tmp expired by the
  reconciler **137.7 s** after `expires_at` (S43 52.3, S42 125.2); the window waited
  889.7 s to pass T1; dev at T1 (rows 1 / main 1, 2), migrated on dev only; the
  second branch refused `branch_limit_reached`; dev reset; `slot3-prod` `ready`.
- **A1′** (slot1–8 `agrees (deleted)`); **B1**: all seven units started by the boot,
  active by **boot+87 s**, 0 failures by themselves; the relay healthy and dev back
  by themselves; `--after-reboot` exit 0.
- **S1** 430 / 3 (D2800, D2801; kept in `/home/op/s44-sweep1/`); E0 again; **S1b**
  (20:59–22:20Z, suite 432 passed, 1 failed in 1:15:42): host **145 claims, 144
  passed, 1 failed** (`documented_path`). The laptop slept overnight; WSL's network
  survived.
- **The branch `--delete-only`** (06:45:45–06:46:16Z, exit 0): dev's names refuse,
  listed after 0. **The external half** (06:47–07:00Z, suite 126 / 5): 31 claims,
  28 passed, 3 failed; **`site_live` PASSED** (D2728 re-earned). **The merge**, with
  224b660's CI offline half (155/155, D2804): **331 claims, 327 passed, 4 failed** —
  `documented_path`, `notifications_live` and `notifications_retrial_live` (D2798),
  `sql_relay_live` (D2799). The operator chose to tag with the three recorded.
- **Tagged 1.22.0 on `224b660`** (tag object `7102e650`, 07:02Z); `publish-cli`
  39915227704 green (contract on the tag, build, publish); PyPI
  `agentic-postgres-cli` `info.version` 1.22.0 (wheel + sdist); `apg --version` →
  `apg 1.22.0` in a clean `python:3.12-slim`.
- **SL4** (07:09Z): `slot8-prod`'s identity `4cd30ff8…` revoked (recorded in
  `/etc/agentic-postgres/slots/slot8-prod/revoked`), its Infisical project kept;
  the credential written by `nano` and shredded, the directory empty; no
  `projects/slot8-prod`. **RC1**: the reconciler active.
- Rows **D2795–D2804**; ADR 0287. **NEXT FREE D2805, ADR 0288.**

### Run 9 — the close

1. **The Ledger**: `sql_editor` → `beta` if `sql_editor_live`, `sql_relay_live`,
   `sql_relay_host` and the six offline `SQL-*` claims passed in
   `evidence/session-44.json`; **no row `trial` at the close** (ADR 0261).
2. **The envelope**: `capacity.ENVELOPE` gains a Session 44 section after
   `:2474` — the relay's footprint (rig 44a, the host's S1 reading), the
   editor-vs-`psql` medians **named as the workstation's**, the role's
   connection counts, each project's release window with its database restart,
   the certificate's issuance time, the sixth re-earning's numbers;
   `UNMEASURED` loses nothing it did not measure.
3. **The documents**: `docs/scope-closure.md` §37 (*What Session 44 closed, what
   it left, and what Session 45 inherits*) in §36's shape; the stage plan's
   Status block re-read and rewritten; this plan's Status line;
   `docs/operator-guide.md`'s 1.22.0 notes (the relay, its name, *"1.22.0
   restarts every database once"*).
4. **The handoff** (outside the repository): the launch folder's `CLAUDE.md` §2
   rows (SESSION 44, RELEASE, EVIDENCE, CURRENT_SESSION, HOST — the relay, the
   `sql` record, `slot8-prod` consumed, **Session 45 needs `slot9-prod`**) and
   **§6's *"A human cannot run SQL through a product surface"* line moved to ADR
   0285's sentence** — copied to the scratchpad first (CLAUDE.md's own rule);
   the project memory's state file.
5. Targeted: `test_reality_ledger`, `test_evidence_claims`,
   `test_documentation_index`, the envelope's test. `bin/session-01-check.sh`
   once (generated artefacts moved). Commit, push, read CI (`contract` and
   `site`).

**Done.** (2026-10-23; WSL `~/s44/run9/`, notes in `NOTES.md`.)

- **The proof repair first** (the operator: *fix the proof, re-run the external
  half*): `e8f0eaa` (test-only, pushed) -- `_pooled` reads the control route the
  deploy publishes; live with `-k` against `224b660`, 4 passed. **The external
  half re-run** from it against the deployed `224b660`: 129 passed, 2 failed;
  **`evidence/session-44.json` merged again: 331 claims, 328 passed, 3 failed**
  -- `documented_path`, `notifications_live`, `notifications_retrial_live`
  (D2807; the first merge kept).
- **D2797 diagnosed** (Sheet IR, a root read-only query): D2805 -- after a wake
  no request follows, the request counter has no series and reads unread, so
  idle sleep never fires. A finding for Session 45.
- **The Ledger** (`close-ledger.py`, `pages-fix.py`, count-asserted):
  **`sql_editor` → `beta`**; **`notifications` → `planned`**, target 45 (D2806,
  the operator's choice), its console view and its site mentions removed, the
  `console` row's text with them; the history paragraph; `docs/reality-ledger.md`
  regenerated. **No row `trial`.**
- **The envelope**: a Session 44 section of eight measurements -- the relay's
  footprint (the rig's 40.49 MiB / 21 pids, the host's 35.4 MiB), the release's
  windows with and without the database restart, the certificate in place 87 s
  into control-prod's window, the editor against `psql` (295.0 / 197.3 ms,
  **named as the workstation's**), the role's connections (2 of 2 pooled, 1 of 2
  direct), the sixth re-earning, D2805's reading, the branches, the suites'
  durations; `docs/capacity-envelope.md` regenerated; `UNMEASURED` unchanged.
- **The documents**: `docs/scope-closure.md` **§37**; the stage plan's Status
  block re-read and rewritten; this plan's Status line; `docs/operator-guide.md`
  -- its release row (stale at 1.21.0 / 43 since Run 7, D2730's class) and **§24
  The SQL relay** (its name, its bounds, *"1.22.0 restarts every project's
  database once"*, a reboot empties its log).
- **The handoff** (outside the repository): CLAUDE.md §2 rewritten for Session
  45 and §6's *"A human cannot run SQL through a product surface"* moved to ADR
  0285's sentence (the file copied to the scratchpad first); the project memory.
- Rows **D2805–D2807**. **NEXT FREE D2808, ADR 0288.**

---

## 7. Evidence and claims

**Expected at the merge** (Run 8): **331 claims** (155 offline). **`failed` 1:
`documented_path`** (D1935). Everything else **passed** — **`site_live`
included** (D2728's repaired recorder, first live run on this evidence), the
Session 38–43 lifecycle, branch and console proofs re-earned at 1.22.0 on
`slot8-prod`, `slot3-prod` and W1′ (D2748, D2749). **Exit 5 for
`documented_path` and no other reason.** Predictions, each moved only by the
evidence.

**The three modes.** Offline: CI's artifact for the deployed SHA (155 claims).
Host: S1 with Session 43's flags renamed (`--lifecycle-record-file` the Session
44 record, `--live-slot-outputs` `slot8-prod`'s K2 copy). External: from WSL
with `--control-outputs`, `--control-probe-file`, `--lifecycle-record-file`,
`--customer-credential-dir` (**the creds directory W1′ updated** — every
reader of it was listed by Session 43's Run 8; Run 6 re-reads the list),
`--console-record-file` (W1′'s) and `--sql-editor-record-file` (E1's). **The
Session 44 customer proofs reach only `routes.control`, the console's origin,
`sql.agenticpostgresql.com` and the public names on 5432, and open no SSH.**
**Deploy every project fully, THEN the dry runs (V1, X0, W0′, E0), THEN W1′ and
E1, THEN the re-earning, THEN sweep, THEN external — every half at one commit;
THEN the tag; THEN the publish.**

**What is not in the evidence, by construction**: the PyPI install (the tag
publishes after the merge) and the site's deployment of the tagged commit (the
`site` workflow runs on the push to `main`, before the tag). Both are recorded in
Run 8's `**Done.**`.

---

## 8. Security invariants this session touches

| Invariant | How this session keeps it |
|---|---|
| **A product surface runs no SQL on the platform's side** (ADR 0246 as amended by 0285) | The statement is typed by the person and sent by the person's browser over the person's own credential; the relay forwards bytes and parses none; no script holds a statement (`test_no_script_holds_sql`, unchanged) |
| **The control plane holds nothing that opens a project's data** | The password never reaches `/v1` (`test_the_password_reaches_only_the_socket`); the relay is not the control plane, holds no credential and reads no secret (`test_the_relay_reads_no_secret_and_no_file`) |
| **A credential shown to or typed by a customer is never logged or stored** | The password in a closure, the input cleared; SCRAM, so neither the relay nor the door sees it; the relay's one log line; the offline and live canaries (D2743) |
| **No third-party script in the console** (D2596) | `pg.js` and `sql.js` are ours; `test_every_asset_is_our_own_file` unchanged (D2732) |
| **The public Postgres port accepts only TLS, routed by name** | The relay speaks TLS to the door with SNI and verify-full; the edge's `sniStrict` is the only router; no entrypoint, port or TLS option changes |
| **PostgreSQL is the final authorization authority** | The role's grants, RLS and `CONNECTION LIMIT` decide; E1 records PostgreSQL's own refusal (D2736) |
| **The connection budget** (ADR 0070) | No new claimant; the editor is a client of the existing doors (D2736) |
| **No published port beyond ADR 0246's list; DNS records naming the host stay DNS-only** | The relay is a route on 443; `sql` is `proxied: false` (D0) |
| **Nothing `planned` has a control** | The editor view lands behind one named exception removed at the bump; the site page lands with the row `trial` (D2746) |
| **A report may not substitute an answer for a failure to determine one** | *Asleep* only from the control API; `4502` *could not be reached*; `unknown` state shown as such (D2737) |
| **The deploy, the sweep and the tag land on one commit** (D1425) | Run 8's order |

---

## 9. Stop conditions

Stop and ask the operator, without improvising, when:

- **Sheet D0** finds a record named `sql.agenticpostgresql.com` already on the
  zone;
- **rig 44a**: the relay's origin receives the console host's cookie, the CSP
  admits a WebSocket to another host, or **Traefik closes an upgraded connection
  carrying traffic before 1,800 s** (D2751 — the cure recreates the shared edge);
- **rig 44b**: SCRAM through WebCrypto does not authenticate, a forged server
  signature is accepted, or **a cancel does not stop a statement through the
  door's shape** in either pool mode;
- **rig 44c**: the relay cannot verify the live door with the image's trust
  store;
- **rig 44d**: `websockets` has a runtime dependency or a non-permissive
  licence, or answers a foreign `Origin` with `101`;
- **the apt pins** expired again and no candidate exists in the index;
- a design here would need the relay to hold a credential, read a mount, call
  `/v1`, parse or rewrite a statement, resolve DNS, or reach any address but the
  edge's entrypoint — **or the page to send the password anywhere but the
  socket, or load a file that is not ours**;
- an editor session would need a role's grants, limits or timeouts changed;
- `upgrade plan` prices 1.22.0 at `major`, or for a reason this plan did not
  name;
- a deploy's window on any project exceeds 5 minutes, a project's routes do not
  return after its R2 sheet, **the relay's certificate is not issued within 5
  minutes of R2d** (no retry), or the relay's router answers any host but its
  own;
- **E1 connects as a role other than the door's**, a role's connection count
  exceeds its `connection_limit`, or **the relay's log holds the walk's marker**;
- a `trial` row would outlive the close, or a row would move to `beta` without
  its claims `passed`;
- a currently-passing test would be weakened to make a new one pass;
- `--render-only` stops working with no host and no root.

---

## 10. Open items this session carries and creates

**Carried, untouched, each still true:** everything in Session 43's §10
*Carried* list (`docs/plans/session-43-implementation-plan.md:2137-2149`) — M7's
X1/X2 (Hetzner) and the store's 443 rule for it (D2640); beta's three rotations
(D1995); D1936/D2005; D1547; D1642, D1798, D1869, D1871, D1722/D1806, D1784,
D1792, ADR 0241's bound; D1045; D1375; D976; D688; D771; D340; D466; D540; D942;
D1203; D1205; D1211; the 24 unclaimed requirements; `process-max` 1 (D593);
`documented_path` (D1935); accounts and organisations never deleted (D2065,
D1986); TOTP seeds plaintext (ADR 0252); `/v1/sessions` unthrottled (D2166,
D2679); the reconciler and the operator serialised by a rule (D2178); a slot's
provider resources outlive it (D2181); the telemetry plane's volumes not backed
up; the plane's footprint at rest `UNMEASURED`; the console's peak on the host
unread; D2724; `lifecycle-s41`…`-s43` empty; the walkers `walk-s43-…` without
membership.

**Created, and named so Session 45 does not inherit them silently:**

- **The relay is a third public surface on the host's 443**, and the first
  long-lived connection the edge carries over HTTP; its outage is the editor's,
  never the doors'. It is charged nowhere (ceilings only, like every
  non-database service).
- **The relay can read every editor session** (D2732, the operator's choice):
  recorded in ADR 0286 and the threat model, canaried live once per trip — a
  change to its logging is a security change.
- **No `statement_timeout` on the customer roles** (D2735): a customer's `psql`
  can hold a statement indefinitely; the editor bounds its own. Adding a role
  timeout is a product decision for a later session.
- **Branch doors are not offered by the editor** (D2738): the relay's grammar
  admits them; listing them is a later page.
- **A verifier from a weak password** set through the raw API is the customer's
  risk (item 25); the console and the CLI never make one.
- **Session 45's walk needs `slot9-prod`**: this session's re-earning consumes
  `slot8-prod` (D2748). **And every release re-earns the lifecycle** (D2714's
  mechanism) — Session 45's release will need a slot for it too, or the walk's
  slot and the re-earning's must be the same one (Session 45's plan decides).
- **The walker `walk-s44-…` remains** without membership; `slot3-prod`'s
  `customer_app` password is the one W1′ set.
- **The `sql` record and its certificate** are one more Let's Encrypt name
  (renewed by the edge like the others).

---

## Appendix — what to consult, how a run is executed here, and the sheets

**Consult, in this order:** CLAUDE.md §1 (the shell traps); this plan's §0, §1
and the run's own text; the reads its run names. **The tree wins.**

**How a run is executed here**: CLAUDE.md §5. Every `sudo` line is the
operator's, on a sheet, under `script -q -e -c '…' /home/op/s44-<sheet>.txt` when
it execs into a container or deploys (D972, D1501), never piped or redirected;
`sudo -v` in the foreground first (D1376). Every `op` line is the agent's over
SSH; remote loops in a script file with `PATH="$HOME/.local/bin:$PATH"`
exported. **`<sha>` is never typed on a sheet**: the agent fills it from `git
rev-parse HEAD` on the host before handing the sheet. **Before any sheet that
deploys: `sudo systemctl stop agentic-postgres-reconciler`, and `start` after**
(D2178); **after any checkout move: restart it** (D2411, D2179). **Read `--help`
of every command on a sheet before handing it** and correct the line to it. **A
sheet may not hand over a command whose precondition is the previous sheet's
success** (D1510): one sheet, one outcome, read before the next. **No secret
value is ever typed into the conversation**: tokens and passwords go into 0600
files by `nano` or into a provider's own form. **Every launcher of a
TOTP-computing instrument runs the checkout's `.venv` python** (D2725).

### Sheet D0 — the relay's name (Run 1; the agent, the operator's decision D2733)

```
(agent, Cloudflare API)  GET  /zones?name=agenticpostgresql.com                 -> zone id
                         GET  /zones/{zone}/dns_records?per_page=100            -> no record named sql.agenticpostgresql.com (else STOP)
                         POST /zones/{zone}/dns_records  {"type":"A","name":"sql","content":"15.204.231.45",
                                                          "proxied":false,"ttl":1,"comment":"apg sql relay (Session 44, D2733)"}
                         GET  /zones/{zone}/dns_records?name=sql.agenticpostgresql.com -> one A, proxied:false
                         GET  /zones/{zone}/dns_records?per_page=100            -> every other record unchanged
(agent, workstation)     nslookup sql.agenticpostgresql.com 1.1.1.1              -> 15.204.231.45
```

### Sheet R1 — the release priced (Run 8)

```
sudo -v
cd ~/agentic-postgres && sudo bin/upgrade.sh plan --project-file /home/op/<each>.yaml   # verb, flags and --also read
                                                                                          # from --help by the agent;
                                                                                          # 'minor': image_digest and the
                                                                                          # reasons the header names
```

### Sheets R2a / R2b / R2c / R2d — 1.22.0 deployed (Run 8; one per sheet, read before the next)

```
# THIS DEPLOY RESTARTS THE PROJECT'S DATABASE (a new Postgres image, D2747).
sudo systemctl stop agentic-postgres-reconciler
script -q -e -c 'sudo ./deploy.sh <the project manifest as Session 43 R2a-c used it>' /home/op/s44-r2<x>.txt
   # R2c: slot3-prod by slot.sh redeploy (refused while the reconciler is active)
   # R2d: control-prod LAST -- the relay starts with it and its certificate is issued
(agent) s44-after.sh <key>: doctor 12 ok; the routes; for R2d the relay container, /__apg/healthz 200, the certificate, the console's policy
sudo systemctl start agentic-postgres-reconciler          # after R2d only
```

### Sheets A1, RA, K1, V1 (Run 8) — as Session 43's (`session-43-implementation-plan.md` §Sheets), the commit and file names moved to 44; RA after the last deploy (D2494).

### Sheets H1, SL1, SL1b, SL2, SL3, RC1, K2, A1′, B1, SL4 (Run 8; D2748) — as Session 43's step 4b (`session-43-implementation-plan.md:1869-1881` and its Run 10 `**Done.**`), `slot7-prod` → `slot8-prod`, every script `~/s44/run6/s44-*`, every file `/home/op/s44-*`; SL4 after the tag, the credential written with `nano` and shredded (D2648).

### Sheets W0′ / W1′ / E0 / E1 — the walks (Run 8; the agent, from WSL, no SSH)

```
(agent) ~/s44/run6/s44-walk.sh --dry      # W0': the console walk to the Connect page, no rotation, the walker removed
(agent) ~/s44/run6/s44-sql.sh --dry       # E0:  sign-in as the probe owner, the editor, SELECT 1 on each door, the refusals
(agent) ~/s44/run6/s44-walk.sh            # W1': the console walk, customer_app rotated, the creds file replaced (.before-s44 kept)
(agent) ~/s44/run6/s44-sql.sh             # E1:  the editor walk, the record, the psql timing
```

### Sheet S1 — the one sweep (Run 8)

```
sudo -v
script -q -e -c 'sudo bash /home/op/s44-sweep.sh' /home/op/s44-s1.txt
   # derived from ~/s43/run8/s43-sweep.sh by diff; the relay's log and peak read by the host module as root
```
