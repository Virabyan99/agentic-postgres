# Session 43 — The public site, the invitation as a link, onboarding in the browser, the console, and the packaged CLI

**Status: EXECUTING — Run 1 DONE 2026-10-19; Run 2 next.** Planned at `bd8f35c` (Session
42's close, tree clean) against the host as read that evening (§0). Rows
**D2650–D2679** at planning; the runs add theirs from **D2680** (Run 1:
D2680–D2687). ADRs **0280–0284** written by Run 1. **NEXT FREE: D2688, ADR 0285.**

The eighth session of Stage 5 and the first of the operator's web-first split
(D2591, D2593): the stage plan's *Session 43* brief as amended
(`docs/plans/stage-5-plan.md` §5 *Session 43*, `:866-951`, *Builds as amended*
`:882-935`, *Must not (added)* `:937-944`, *Measures (added)* `:946-949`,
*Closes (amended)* `:951`) — **a public site on Cloudflare Pages, the customer
documentation published there, the invitation as a link, onboarding and TOTP in
the browser, the console over `/api/v1`, and the customer CLI installable from
PyPI** — with the three choices the operator took on 2026-10-18 (D2594 PyPI by
trusted publishing, D2595 the console's cookie, D2596 no third-party script),
**the four the operator took at this planning on 2026-10-19** (§1 D2650, D2652,
D2653, D2654), and what Session 42 handed it (`docs/scope-closure.md` §35,
*"What Session 43 inherits, in order"*, `:1693-1702`): **D2636, D2637, D2642**,
each *"a redeploy of four"* — they ride this session's release (D2670).

Eleven runs and **one sitting** on the host. **Run 1** is documentation, three
operator sheets in the Cloudflare and PyPI consoles, one agent act on the
Cloudflare zone, five rigs and five ADRs. **Runs 2–8** change code. **Run 9** is
the bump. **Run 10** is the sitting: the release on the four projects (the
console appears on `control-prod` only), the dry run, the browser walk, the
sweep, the external half, the merge, the tag — and the tag publishes the CLI to
PyPI. **Run 11** is the close. **No slot is created, no reboot is taken, no
database restarts** (D2671).

**Brief:** `docs/plans/stage-5-plan.md` §5 *Session 43* (`:866-987`, the old
text `:953-987` kept as written and read as amended by D2591/D2593); §7's table
row 43 (`:1140`); §8's invariants (`:1159-1193`, the row *A product surface runs
no SQL* `:1171`); §9's stops (`:1197-1241`); §11 (`:1292-1358`).
`docs/scope-closure.md` §35 (`:1647-1702`). Session 42's plan §10, both lists
(`docs/plans/session-42-implementation-plan.md:1790-1838`), and its rows
**D2591–D2596** (`:476-481`) and **D2634–D2649** (`:524-539`). ADRs **0069**
(the docs container's own CSP), **0093** (a `bin/` command imports only
`agentic_postgres` and `yaml`), **0171** (a deterministic token digest), **0195**,
**0205** (Studio: same-origin forwarder, loopback), **0246** (the hosted
boundary), **0251–0254** (the control plane, accounts and TOTP, keys, the
Ledger's operation gate), **0268** (the public Postgres door), **0274** (plans).
`docs/reality-ledger.yaml` rows `console` (`:196-211`), `sql_editor`
(`:944-957`), `cli_remote` (`:172-194`), `management_api` (`:151-153`),
`plan_free` (`:822-852`), `plan_premium` (`:854-875`), `billing`
(`:1035-1047`). `docs/threat-model.md` hosted items (`:184-381`).

**Shape:** eleven runs. **Run 1** reads **no** CI verdict (documentation; the
zone act and the consoles are recorded in its `**Done.**`). **Runs 2–8** each push
and read that commit's own CI verdict by full SHA (`gh api
"repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" -R
Virabyan99/agentic-postgres --jq '.workflow_runs[] | [.name, .status,
.conclusion] | @tsv'` from Git Bash, never inside `wsl`; judged on HTTP status,
three buckets — success / failure / not registered; an empty list is not a
verdict, D1057). **From Run 7 on, a push to `main` also starts the `site`
workflow after `contract` succeeds** (D2653): its verdict is read the same way,
by the same SHA, and it is a second line in the same listing. **Run 9** is the
bump. **Run 10** is the sitting. **Run 11** is the close (Ledger and envelope
rows are code: it reads CI). **Push only after the previous commit's CI lands**
— `ci.yml` cancels in-progress runs on `main` (`.github/workflows/ci.yml:36-38`).

**Product version at close:** `CURRENT_SESSION` **43**; `template_version`
**`1.21.0`** — predicted *minor* (**no** project-manifest, outputs, host or lock
schema change, no new secret, no released migration, no control-set migration;
one new compose service under a facility profile on the control project only; a
changed control API — a cookie mode, an `accept_url` member, a QR member; a new
environment variable rendered for the control project) and **read from `upgrade
plan` on the host, never chosen** (Sheet R1). Released migrations stay **39**;
the control set stays **9**. **One new compose service (`console`, profile
`console`, control project only), one new image (`services/console/`), two new
`bin/` commands (`bin/build-site.py`, `bin/build-cli.py`), two new workflows
(`.github/workflows/site.yml`, `.github/workflows/publish-cli.yml`), one new
top-level directory (`site/`). No new published port, no new edge route outside
the control project's own host, no edge recreate.** A `major` is §9's stop.

**Written for whoever picks this up cold, and it will be a different model than
the one that planned it.** Every path below was read from the tree on 2026-10-19
at `bd8f35c` — three explore passes (the control API and its serving; the docs,
the Ledger, plans, packaging and CI; the registry, claims, gates and guards) and
direct reads of `services/docs/serve.py` whole, `services/docs/Dockerfile` whole,
`services/auth-api/app/models.py:95-150,521-595`,
`services/auth-api/app/control_routes.py:186-300`,
`services/auth-api/app/control_service.py:370-395`,
`src/agentic_postgres/scram.py:25-52`, `src/agentic_postgres/plans.py` whole,
`compose.yaml:720-770`, `bin/telemetry.sh:165-178`, `bin/provision-host.sh:330-340`,
`bin/bootstrap-providers.py:1022-1030`,
`services/auth-api/app/one_time_tokens.py:10-20`,
`tests/contract/test_reality_ledger.py:245-265` — **and the readings taken at
planning** (§0). Every path is cited `path:line`. **Read CLAUDE.md §1 in the
launch folder before the first command, then this plan's §1, then the
appendix.** If a step here and the tree disagree, **the tree wins and the
disagreement is a divergence row** (next free `D` after §1's table), never a
silent reconciliation. **When this plan names a line number, open the file at
that line and read the surrounding twenty lines before editing** — the numbers
were right on 2026-10-19 and `ruff format` moves them.

**The twelve sentences the executor most needs, in case nothing else is read:**

1. **The console is a first-party static server on the control project's own
   origin**, built the way the docs container is (`services/docs/serve.py`: a
   fixed route table, no path joining, its own Content-Security-Policy) — a new
   `services/console/` image and a `console` compose service under a FACILITY
   profile `console` that `bin/project-runtime.sh` adds only for the control
   project (the `public-endpoints` shape, `bin/project-runtime.sh:114-127`,
   D2344). It holds no credential, runs no SQL and calls `/api/v1` only (D2655,
   ADR 0280).
2. **The session in the browser is a pair of `__Host-` cookies** —
   `HttpOnly; Secure; SameSite=Strict; Path=/` — set by the EXISTING session
   routes when the request carries `X-Apg-Console: 1`; the JSON body then holds
   no token. A cookie is honoured only with that header, and a write only when
   `Origin` is the console's origin. **A request with `Authorization` is bearer
   mode and ignores cookies: the CLI and API keys are unchanged** (D2656, ADR
   0281).
3. **The invitation is a link whose token is in the fragment**:
   `https://control.agenticpostgresql.com/accept#<token>`. The mint answer
   gains `accept_url`; `org invite --output` writes the link; `login accept
   --invitation-file` reads a token or a link; the accept page removes the
   fragment from the address bar before its first request (D2657, ADR 0282).
4. **The TOTP QR is drawn by the server** as an SVG data URI (`segno`, pinned,
   hash-locked into the auth image), returned beside `secret` and `otpauth_uri`
   in the enrolment answer that is already shown once; the page shows it as an
   `<img>` and the base32 text under it. No QR script runs in the browser (D2659,
   ADR 0282). **Confirming a factor ends every session** (`control_service.py:396-422`):
   the onboarding page logs in again with the code.
5. **The browser never sends a database password**: like the CLI
   (`bin/cloud.py:1001`, `:1176-1185`) it generates the password, sends only its
   SCRAM-SHA-256 verifier (WebCrypto PBKDF2, `services/console/scram.js`, proved
   equal to `agentic_postgres.scram.verifier` with a fixed salt), and shows the
   password once (D2660).
6. **Every console page maps to a Ledger row that is `trial`, `beta` or
   `available`, and every `/v1` path it calls exists in
   `contracts/control-openapi.canonical.json`** — the guard that replaces
   `test_no_console_exists_yet` (`tests/contract/test_reality_ledger.py:251-262`;
   a contract test changed under ADR 0280). **No Studio view, no SQL, no
   `planned` page** (D2661).
7. **The site is static files built from the repository** by `bin/build-site.py`
   (pages in `site/pages/*.md`, rendered by an in-house Markdown SUBSET that
   refuses raw HTML, D2663); the pricing page reads `plans.PLANS` and
   `plans.BETA_SENTENCE` at build time and types no number (D2664); every page
   names its Ledger rows in its front matter and the build refuses a row that is
   not reachable, a §59 word (`reality_ledger.FORBIDDEN_WORDS`), `bin/`, `sudo`,
   `ssh` or a clone (D2662). Two builds of one tree are byte-equal.
8. **The site reaches Cloudflare Pages only from CI**: `.github/workflows/site.yml`
   runs on `workflow_run` of `contract` succeeding on `main`, builds, and uploads
   with a pinned wrangler using a Pages-only API token held as a GitHub
   ENVIRONMENT secret (D2653, ADR 0283). The apex and `www` are Pages custom
   domains — proxied records Cloudflare hosts, which the grey-cloud rule (made
   for the host's ACME and its Postgres port) does not cover (D2651).
9. **The CLI is published as `agentic-postgres-cli`, command `apg`**, staged by
   `bin/build-cli.py` from `bin/cloud.py` (a marked import seam replaced),
   `src/agentic_postgres/control_client.py` and `src/agentic_postgres/scram.py`
   — one source, no committed copy; **`plans` leaves the CLI** (the interest
   check reads `GET /v1/plans`). Published by `.github/workflows/publish-cli.yml`
   only from a release tag whose `contract` run succeeded, by PyPI trusted
   publishing — no token anywhere (D2666, D2667, ADR 0284).
10. **The foreign Worker route `*.agenticpostgresql.com/*` and the wildcard
    AAAA are removed in Run 1** — the operator's decision of 2026-10-19 (D2650);
    the Worker script itself is not this project's and is not touched.
11. **The browser walk is Playwright in its pinned image**, driven by
    `tests/external/browser/console_walk.py`, writing a record the external
    proofs read through a new gate `APG_CONSOLE_RECORD_FILE` (D2668). Its
    subject is `probe-s37`'s `slot3-prod`: a NEW admin invited by link, onboarded
    with TOTP in the page, rotating `customer_app` from the Connect page and
    connecting over TLS with the password the page showed once (D2669). **No
    slot is prepared in this session.**
12. **D2636, D2637 and D2642 are Run 2's, each with a failing test first**
    (D2670): `telemetry.sh status` reads a container with no healthcheck;
    `provision-host.sh --check` reads the launchers from the glob the install
    reads; `bootstrap-providers` prints the count it created.

---

## 0. Where the session starts

```
HEAD            bd8f35c on main, local = origin ("docs(session-42): the close's
                gate and CI recorded"), tree clean. Code: f798af8 (CI
                39268848957 success). Deployed AND TAGGED: 77303e4 (1.20.0, tag
                object 747fe5a) on all four projects. main is past the tag with
                de3d204 (a proof's expected role, D2645) and the close (the
                Ledger to beta, the envelope) -- NOT deployed; no product
                behaviour differs.
VERSION         1.20.0 (VERSION; read by src/agentic_postgres/__init__.py
                template_version() :1278-1284). CURRENT_SESSION 42 (:1270; Session
                42's paragraph :1207-1269). README.md:7 "Session 42 implemented",
                at template_version 1.20.0 (guarded by
                tests/contract/test_documentation_index.py:170-212). Outputs 22,
                project manifest 1-11, host.yaml 2|3|4, 39 released migrations,
                the control set 9.
REGISTRY        395 requirements (tests/acceptance-registry.yaml, 8,030 lines;
                Session 42's block :7762-8030). ID regex
                tests/contract/test_acceptance_registry.py:127 (prefixes end
                ...|PLAN|USE|INS; Session 42's comment :124-126). No CON, SITE,
                WEB, PKG or DOC prefix exists (CONN does). 302 claims
                (src/agentic_postgres/evidence_claims.py CLAIMS :532-1472,
                Session 42's block :946-969); 133 offline (OFFLINE_CLAIMS
                :106-485, Session 42's :458-483). CLAIM_INTRODUCED_IN
                tests/contract/test_evidence_claims.py:953-1345 (42's :1290-1307).
                279 ADRs (docs/decisions/README.md last row :345 = 0279).
                NEXT FREE: D2650, ADR 0280.
EVIDENCE        evidence/session-42.json (WSL, gitignored): 302 claims, 301
                passed, 1 failed -- documented_path (D1935).
LEDGER          docs/reality-ledger.yaml (1,189 lines, 43 rows): beta 24,
                planned 9 (console -> 43; wake_on_connect, email, passkeys -> null;
                project_isolation, agents, workflows, connectors, audit -> 38),
                not_offered 9 (sql_editor among them), not_metered 1, trial 0.
                schemas/reality-ledger.schema.json target_session max 43 (:121-128).
GATES           bin/session-42-check.sh 2,176 lines (readonly SESSION=42 :106;
                usage :182-; mode_offline :1632-1849, mode_host :1851-2069,
                mode_external :2071-2165). tests/contract/
                test_session_forty_two_gate_modes.py 1,103 lines (SESSION = 42
                :56, SESSION_PREVIOUS_NUMBER = 41 :71, claims :82-).
                SHELL_COMMANDS tests/contract/test_cli_contract.py:42-286
                (session-42-check.sh :265); PYTHON_COMMANDS :288- (cloud.py :304).
                The environment roster tests/conftest.py:86-225 (last entry
                Session 40's APG_BRANCH_RECORD_FILE :224).
HOST            15.204.231.45 (apg-ovh-01), read 2026-10-19 17:43Z (§0 p1-p4).
OPERATOR        2026-10-19 (this planning): the Worker route removed (D2650);
                PyPI name agentic-postgres-cli (D2652); the site by CI direct
                upload (D2653); the invitation address a domain alias by
                Cloudflare Email Routing (D2654).
```

**What exists, measured at `bd8f35c`, and the session builds on:**

- **The control API** (`services/auth-api/app/control_routes.py`, 1,489 lines;
  `APIRouter(prefix="/v1")` `:71`; every answer through `_guard`, which adds
  `Cache-Control: no-store`, `:75`, `:137-152`). **48 operations on 41 paths**
  (the snapshot `contracts/control-openapi.canonical.json`; the path list also
  in `services/auth-api/app/main.py:478-529`). Roles from
  `control_roles.MATRIX` keyed by handler name (`control_roles.py:48-117`);
  `KEY_SCOPES` `:199-238`; a key on any other route is `403
  human_session_required` (`control_service.py:329-331`). The routes the
  browser path uses:
  - `POST /v1/sessions` `create_session` `:192` (PUBLIC; body
    `ControlLoginRequest` `models.py:521-530` — `username`, `password`,
    `totp_code` optional; refusals `authentication_failed`,
    `second_factor_required`, `second_factor_invalid`); answer
    `SessionTokenResponse` (`models.py:108-119`: `access_token`, `token_type`,
    `expires_at`, `token_use`, `refresh_token`) built by `_tokens`
    (`control_routes.py:155-164`). The access token is an RS256 JWT
    (`keys.py:34`), `exp = now + 900` (`service.py:37`, `:308`); the refresh
    token is `token_urlsafe(32)`, stored as SHA-256 (`one_time_tokens.py:37`,
    `:51-63`), 30 days (`refresh_sessions.py:77`), single use, rotated.
  - `POST /v1/sessions/refresh` `:222` (body `RefreshRequest` `models.py:95-105`,
    `refresh_token` only); `DELETE /v1/sessions/current` `:248` (body
    `refresh_token`, 204).
  - `GET /v1/me` `:272` → `control_service.me` (`:370-383`: `user_id`,
    `username`, `display_name`, `second_factor {enabled, required}`,
    `organizations [{id, role}]`). `POST /v1/me/totp` `:298` →
    `begin_factor` (`control_service.py:387-394`: `{secret, otpauth_uri}`;
    model `FactorEnrolmentResponse` `models.py:545-549`); `POST
    /v1/me/totp/confirm` `:324` (`ConfirmFactorRequest` `models.py:539-542`;
    answer `{"enabled": true, "sessions_ended": n}`; **ends every refresh
    family**, `control_service.py:396-422`). TOTP: `totp.py` (seed 20 bytes
    `:58`, issuer `:61`, step `:45`, URI `:131-141`); the factor is required for
    owners, admins and `admin_users:write` (`control_roles.py:264-273`); seeds
    stored plaintext (`projects/control/migrations/templates/0001-control-identity.sql:104-115`, ADR 0252).
  - `POST /v1/invitations` `mint_invitation` `:363` (`MintInvitationRequest`
    `models.py:560-566`: no organisation and no role = an ACCOUNT invitation,
    both = a MEMBERSHIP invitation; answer `InvitationResponse` `:569-576`:
    `id, invitation_token, organization_id, role, expires_at` — **a bare token,
    no URL anywhere**; minted at `control_service.py:452`, answered `:456-462`;
    default 72 h, max 168, `:86-87`, `:214-222`). `POST /v1/invitations/accept`
    `:400` (PUBLIC, bearer optional `:404`; `AcceptInvitationRequest`
    `models.py:579-590`: the token alone for a signed-in caller, or token,
    `username`, `display_name`, `password`).
  - Project, branch, backup, usage, insights, monitoring, plan, notification
    and settings routes `:680-1481` (the table in §5 Run 5).
  - **Authentication** (`_caller`, `control_routes.py:106-110`) reads only
    `request.headers.get("authorization")` → `ControlService.authenticate`
    (`control_service.py:292-310`: strips `Bearer `; `apg_…` is a key
    `:297`, `:312-343`; else `AuthService.authenticate`, `service.py:329-342`);
    the factor gate `control_service.py:345-350`. **No `set_cookie`, `Cookie`,
    `StaticFiles`, `FileResponse`, `HTMLResponse`, CSP, HSTS, `CORSMiddleware`
    or `Origin` check in control mode** (the only `Origin` refusal is the MCP
    mode's `mcp_origin.py:51`). `main.py:403-404` adds `StructuredRequestLog`
    and `StampRequestId` only.
- **How the control project is served.** `APP_MODES`
  (`services/auth-api/app/settings.py:41`); control mode mounts `/auth/me` and
  the router (`main.py:333-349`), `docs_url`/`redoc_url`/`openapi_url` `None`
  (`:301-303`). Rendering sets `AUTH_APP_MODE=control` (`src/agentic_postgres/rendering.py:2239`)
  and emits `API_CONTROL_PATH`, `CONTROL_ROUTE_PATH`, `CONTROL_ROUTER_NAME`,
  `CONTROL_STRIPPREFIX_MIDDLEWARE_NAME` (`:2240-2243`; `compose.yaml:1515`). The
  router `apg-<key>-control` (`naming.py:420-428`), its strip middleware
  (`:431-438`), `CONTROL_PATH_SUFFIX = "/v1"` (`:127`), the route path
  `{api_base_path}/v1` (`:1410-1412`). Labels: `_control_labels`
  (`src/agentic_postgres/runtime_override.py:1508-1544`), rule
  ``Host(PROJECT_DOMAIN) && (Path(`/api/v1`) || PathPrefix(`/api/v1/`))``,
  middlewares the baseline chain, buffering, the strip; attached to the control
  project's `auth` container (`:929-942`). **Nothing answers `/`** (every rule is
  a specific `Path`/`PathPrefix`: `runtime_override.py:801, 1309, 1369, 1415,
  1483, 1533, 1629, 1713, 1763`), so `/` is Traefik's own 404 with no chain
  (`infra/edge/dynamic/baseline.yaml:76-79`). The baseline: `apg-security-headers`
  (nosniff, `frameDeny`, `referrerPolicy: no-referrer`, HSTS substituted by
  `bin/render-config.py:316-329`) `baseline.yaml:42-48`, `apg-response-policy`
  (`Cache-Control: no-store`, `Server` removed) `:80-84`, `apg-rate-limit`
  (average 20/s, burst 40) `:54-58`, `:89-94`. **The access log drops the
  `Authorization` and `Cookie` headers** (`infra/edge/traefik.yaml:155-159`).
- **The docs container — the console's model.** `services/docs/serve.py`
  (245 lines): `ROUTES` a fixed table (`:76-85`), `REDIRECTS` relative
  (`:91-94`), `HEALTH_PATH` (`:96`), `CONTENT_SECURITY_POLICY` (`:109-121`,
  `default-src 'none'` first; `style-src 'self' 'unsafe-inline'` a concession for
  Scalar), `SECURITY_HEADERS` (`:123-133`: CSP, `Referrer-Policy: no-referrer`,
  nosniff, `X-Frame-Options: DENY`, COOP and CORP `same-origin`, `Cache-Control:
  no-store`), `log_message` naming no header and no query (`:143-150`), GET and
  HEAD only. `services/docs/Dockerfile` (74 lines): two stages, both bases as
  build arguments from `versions.env` (no default), uid 65532, healthcheck
  through `urllib` `:69-70`, exec-form entrypoint. The compose service `docs:`
  `compose.yaml:1153-`. Tests: `tests/contract/test_docs_service.py`.
- **Studio** (ADR 0205): `bin/studio.py` (876 lines) on `127.0.0.1` only, a
  launch cookie `HttpOnly; SameSite=Strict` (`bin/studio.py:493-494`), Host,
  Origin and `X-Apg-Studio` checked (`:11-12`, `:453`), its CSP
  (`src/agentic_postgres/studio.py:152-161`). **It is not a container and is
  never published.**
- **The facility profile.** `compose.yaml:728-767`: `customer-pool` and
  `customer-direct` carry `profiles: [public-endpoints]`, which
  `bin/project-runtime.sh:114-127` adds only when the render says
  `APG_PUBLIC_ENDPOINTS=1` (`rendering.py:735`, `runtime_override.py:1018`;
  D2344).
- **The customer CLI.** `bin/cloud.py` (1,799 lines): `REPO_ROOT` and the
  `sys.path` insert `:82-83`; imports `control_client as cc`, `plans`, `scram`
  `:85-87` (otherwise stdlib only, `:65-81`); `read_invitation` `:147-151`
  (one whitespace-free token from a 0600 file through `read_private_file`);
  `deliver_secret` `:223-229`; `login accept` `:314-362`; `totp-enroll` `:365-382`
  (prints `otpauth_uri` and `secret`; a non-TTY stdout refused; **no qrencode** —
  only `docs/operator-guide.md:2113-2115` uses it); `org invite` `:485-500`
  (`--output` required; writes the token); `project create` builds both
  customer verifiers `:1176-1185`; credential rotation sends `{"role",
  "verifier"}` `:1001`; `endpoint connect` runs `psql` `:1062`;
  `INTEREST_PLANS` from `plans.PLAN_NAMES` `:1297-1298`; the parser
  `:1508-1755`; `main(argv=None)` `:1783`; `if __name__` `:1798`. Fourteen
  shims exec it (`login, logout, context, org, project, compute, operation,
  endpoint, branch, plan, usage, notifications, insights, monitoring`; asserted
  `test_cli_contract.py:1348`, `:1380-1383`). `tests/contract/test_control_cli.py`
  loads it by path (`:971-974`, `spec_from_file_location("apg_cloud", BIN /
  "cloud.py")`). `src/agentic_postgres/control_client.py` (469 lines) and
  `src/agentic_postgres/scram.py` (52 lines; `verifier(password, *, salt=None)`
  `:40-52`, `ITERATIONS = 4096`, `SALT_BYTES = 16`, `VERIFIER` regex `:30-32`)
  import the standard library only. **`src/agentic_postgres/plans.py`** re-exports
  `services/auth-api/app/plans.py` through `service_source.load` →
  `REPO_ROOT / "services" / "auth-api"` (`service_source.py:37-46`): **it cannot
  travel in a wheel**. State: `${XDG_CONFIG_HOME:-$HOME/.config}/apg/`
  (`control_client.py:6-13`, `:78-86`, `:106-114`); https only except loopback
  (`:217-229`); redirects refused (`:308-318`).
- **Plans** (`services/auth-api/app/plans.py`, 107 lines, stdlib only):
  `PLAN_NAMES` `:43`, `DEFAULT_PLAN` `:45`, `BETA_SENTENCE` `:48-52` (*"Free is the
  plan every organisation has during the beta. Premium is defined and not
  available during the beta: its limits are shown, and Notify me records that you
  asked. Nothing is charged."*), `Entitlement` `:55-64`, `Plan` `:67-71`,
  `PLANS` `:76-103` (free `active`, premium `unavailable_during_beta`; six
  entitlements each). **No price and no currency anywhere.**
- **The Reality Ledger.** `src/agentic_postgres/reality_ledger.py` (291 lines):
  `STATUSES` `:45`, `REACHABLE = {available, beta, trial}` `:50`,
  `FORBIDDEN_WORDS` `:59-68` (`production-ready`, `enterprise-grade`, `highly
  available`, `fault tolerant`, `multi-region`, `serverless`, `autoscaling`,
  `zero downtime`), `load`/`validate` `:77-98`, `forbidden_words_in` `:206`,
  `render` `:221`; `bin/render-reality-ledger.py --check|--write` (run by
  `bin/session-01-check.sh:231`) writes `docs/reality-ledger.md` (778 lines).
  The guard `tests/contract/test_reality_ledger.py` (`:51` … `:266`;
  **`test_no_console_exists_yet` `:251-262` asserts `services/console` does not
  exist** and says the session that builds it replaces it). The services cannot
  read the file (`services/auth-api/app/operations.py:28`). **No `/v1/ledger`
  route** (`docs/control-plane.md:310`).
- **The customer documentation today** is sections of operator-adjacent pages:
  `docs/managed-projects.md` (349 lines; *"This page is the customer's"* `:6`;
  42 lines naming `bin/`; `sudo bin/doctor.sh usage` `:295`; sections Connecting
  `:158`, Backups `:173`, Branches `:194`, Plans `:246`, Usage `:272`, Query
  Insights and monitoring `:304`, Notifications `:323`, Refusals `:337`);
  `docs/control-plane.md` (311 lines; customer commands `:128-177`, operator
  `sudo bin/control.sh` `:83`, `:107-108`, `:175-177`; the invitation file
  `:130-131`; *"no web console, no rate limit on `/v1/sessions` …"* `:308-311`);
  `docs/monitoring.md` (customer `:1-70`, operator from `:71`);
  `docs/database-connections.md` (customer `:69-108` only). The documentation
  guards: `test_documentation_index.py` (every `docs/*.md` linked once from
  `docs/README.md`, `:454-486`; README's session and version `:170-212`);
  `test_session12_documented_path.py` (`CURRENT_PATH_DOCUMENTS` `:33-67`; neither
  `managed-projects.md` nor `control-plane.md` is in it).
- **Packaging and CI.** `pyproject.toml` (53 lines): `name =
  "agentic-postgres"` `:2`, `requires-python = "==3.12.*"` `:4`, version from
  `VERSION` `:11-12`, setuptools `:7-9`, packages from `src` `:14-15`, **no
  dependencies, no `[project.scripts]`**. `requirements-dev.in`/`.txt`
  hash-locked by `bin/lock-dev-deps.sh` (`exclude-newer: 2026-09-03T15:16:21Z`;
  `test_repository_contract.py:553`). **No `uv.lock`, no `dist/`, no build.**
  `.github/workflows/ci.yml` (366 lines, `name: contract` `:13`): push to `main`
  and `session-*` `:16-29`, `pull_request` `:30`, `workflow_dispatch` `:31`;
  **no tag trigger**; `permissions: contents: read` `:33-34`; concurrency
  `contract-${{ github.ref }}`, cancel-in-progress `:36-38`; jobs `gate`
  `:41-141` (setup-uv `0.12.1`, `uv venv` + `pip install --require-hashes`,
  `bin/session-01-check.sh`, offline evidence artifact), `session-2-contract`
  `:143-311`, `future-inventory` `:313-365`. **No publish, release, PyPI, Pages
  or Cloudflare job.** Workflows are read by `test_gate_contract.py:163, 208-235,
  289, 322` (a session compared to a literal fails), `test_dev_environment.py:1075`,
  `test_client_typescript.py:450`; `ci.yml` is in `REQUIRED_PATHS`
  (`test_repository_contract.py:42`).
- **The repository's other guards a new directory meets**:
  `test_repository_contract.py` has **no top-level allowlist**; `SCAN_ROOTS`
  `:276`; `test_no_module_is_imported_only_by_its_own_tests` `:616-650` (a new
  `src/agentic_postgres/*.py` needs a `bin/` caller); `test_no_tracked_file_uses_crlf`
  `:393`. **The gate's step 1 fails on any untracked file**
  (`bin/session-01-check.sh:85-90`) — build output must land outside the tree or
  under an ignored path. `.gitignore` ignores `.generated/*`, `evidence/*`, the
  venv and caches, the operator inputs; **no `dist/` or `build/`**. Ruff runs on
  `src bin tests` (`bin/session-01-check.sh:119-120`); shellcheck on `deploy.sh
  bin/*.sh bin/lib/*.sh libexec/* infra/secret-store/*.sh` (`:118`).
- **The three repairs owed.** `bin/telemetry.sh` `do_status` `:165-178`: the
  inspect template already carries `{{if .State.Health}}` and still exits 1 on
  the healthcheck-less gateway (D2636 measured `map has no entry for key
  "Health"`); `bin/provision-host.sh:330-340`: the launcher check loops a TYPED
  `edge project firewall ssh-rollback database-access` while the install globs
  `libexec/agentic-postgres-*` (six) (D2637); `bin/bootstrap-providers.py:1027`:
  `print(f"bootstrap-providers: created 4 resource(s) for {key}")` — a literal
  (D2642).
- **The threat model** (`docs/threat-model.md`, 407 lines): the `THR-*` table
  `:17-68` (48 rows; the newest `THR-INS-POISON` … `THR-INS-UI` `:65-68`); the
  hosted list `:184-381` (items 1–15, **13 numbered twice**, `:338` and `:354`);
  `## Scope` `:383`.
- **The envelope.** `src/agentic_postgres/capacity.py` `ENVELOPE` `:113-2337`
  (Session 42's section `:2106-2336`); `UNMEASURED` `:2346-2437`.

**Measured at planning** (2026-10-19; no rig was run — every third-party fact
this plan relies on is Run 1's, §5):

| # | Reading | Result |
|---|---|---|
| p1 | `apg-diag containers` (agent, 17:4xZ) | exit 0; **45 healthy** (alpha-dev ×10, beta-dev ×10, control-prod ×10, slot3-prod ×12, the plane's ClickHouse, HyperDX, MongoDB healthy and the gateway `Up` with no healthcheck); no branch |
| p2 | `apg-diag listeners` | 22, 80, 443, 5432 (+ the resolver's 53, chrony 323, DHCP 68) — unchanged since Session 42 |
| p3 | op: checkout, status, `free -m`, `uptime`, units | `77303e4f32957f094b01c50b2f183c356cf0b516` clean; total 11,671, **available 8,189 MiB**; up 7 h 07; the reconciler, the edge and the telemetry units `active` |
| p4 | `curl` from the workstation (Windows, 17:41Z) | `https://agenticpostgresql.com/` **does not resolve** (curl exit 6; no apex record); `https://www.agenticpostgresql.com/` **404 `application/json` from `Server: cloudflare`** (188.114.96/97.x); `docs.agenticpostgresql.com` resolves to the same Cloudflare addresses; `https://control.agenticpostgresql.com/` and `/api/v1/` **404 `text/plain` from 15.204.231.45** (Traefik's own) |
| p5 | Cloudflare API (agent, read-only): the zone `agenticpostgresql.com` | `active`, plan **Free Website**, SSL mode `full`; 24 records — every A record DNS-only (`proxied: false`) to 15.204.231.45 (control, alpha-db, beta-db, slot1–6, pool./direct. slot2–6, `*.pool.slot3`, `*.direct.slot3`), `secrets.` → 15.204.66.146, `snippets-db.` → 2.28.74.158 — **and one proxied `AAAA *.agenticpostgresql.com → 100::`** |
| p6 | Cloudflare API: Workers routes on the zone; scripts | **one route `*.agenticpostgresql.com/*` → script `forgeai-sandbox`** (created 2026-09-18, modified 2026-09-19, a `fetch` handler; not this project's — 0 hits for `forgeai` in the tree). No Workers custom domain. It answers every proxied subdomain (p4's `www.`, `docs.`); grey records bypass it |
| p7 | Cloudflare API: Pages projects on the account | ten, none of this product's (`workers-ai-image-playground`, `p2p-*`, `rf-mini-course`, `miro-clone-v1`) |
| p8 | `https://pypi.org/pypi/agentic-postgres/json`, `…/agentic-postgres-cli/json`, `/simple/…/` | **404 for all four** — neither name exists on PyPI; **the name is not claimed yet** |
| p9 | The repository: `site/`, `services/console/`, `dist/`, `uv.lock`, a `[project.scripts]`, a tag-triggered workflow | none exists |

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `bd8f35c`** (or the
zone, PyPI and the host as the planning readings left them) set against what
the brief says, with the decision this plan takes. **Next free number after
this table is D2680.** Rows the runs add go in a second table below it, in
execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2650** | Stage plan `:892-893`: *"published to Cloudflare Pages on the apex and `www`"*. | p5, p6: a Worker `forgeai-sandbox` — not this project's — holds the zone route `*.agenticpostgresql.com/*`, and a proxied wildcard `AAAA * → 100::` sends every unlisted name through it; `www.` and `docs.` answer its JSON 404 today. Worker routes run in front of whatever a proxied hostname serves; a Pages custom domain on `www` would sit behind it. The apex is not matched by `*.` and has no record. | **The operator, 2026-10-19: remove both.** **Sheet C0 (Run 1, the agent through the Cloudflare API, recorded)**: re-read the route and the record by id (they must equal p5/p6 — anything else is §9's stop), `DELETE /zones/{zone}/workers/routes/{route_id}`, `DELETE /zones/{zone}/dns_records/{aaaa_id}`, read both absent, then `curl -sI https://www.agenticpostgresql.com/` → no answer (does not resolve). **The script `forgeai-sandbox` is NOT deleted** (it is not this product's; only its claim on this zone goes). | A product's own zone answers only what the product publishes; a wildcard someone else's code serves is the place a stranger's first request would land. | 0283 |
| **D2651** | Stage plan `:896-899`: *"The plan decides — and records as an ADR — that a Pages custom domain is a Cloudflare-hosted record, which the grey-cloud rule … does not cover."* | CLAUDE.md §6: *"DNS records stay grey-cloud."* Every host record is DNS-only (p5) because ACME HTTP-01 and the Postgres port (ADR 0268) need the host's own address. A Pages custom domain is a CNAME Cloudflare creates **proxied** (it must be: Pages is served by Cloudflare's edge); the apex form is CNAME-flattened. | **ADR 0283 scopes the rule**: *a record that names the production host stays DNS-only; a record Cloudflare Pages creates for the public site is proxied and names no host of ours.* A guard (`tests/contract/test_site.py::test_the_site_names_no_host_address`) asserts the site's build and its workflow hold no host address and no `*.agenticpostgresql.com` name but the apex, `www` and `control`. Sheet C4 (Run 7) attaches `agenticpostgresql.com` and `www.agenticpostgresql.com` to the Pages project through the API and reads both CNAMEs back `proxied: true`, and every host A record still `false`. | The rule protects the host's certificate and its Postgres door; a static site Cloudflare serves has neither. | **0283** |
| **D2652** | D2594: *"The operator claims the name on PyPI before Session 43 runs … candidates `agentic-postgres`, `agentic-postgres-cli`; Session 43's plan reads which was claimed."* | p8: **neither exists** — nothing was claimed. PyPI's *pending publisher* (trusted publishing registered for a project that does not exist yet) is believed **not to reserve the name** until the first upload — **Run 1 reads PyPI's documentation and records the sentence, never assumes it**. The root `pyproject.toml` is already named `agentic-postgres` (`:2`) and is never published. | **The operator, 2026-10-19: `agentic-postgres-cli`, the installed command `apg`.** **Sheet C2 (Run 1, the operator in pypi.org)**: a pending publisher — project `agentic-postgres-cli`, owner `Virabyan99`, repository `agentic-postgres`, workflow `publish-cli.yml`, environment `pypi`. The first upload is Session 43's tag (Run 10). **If the name is taken by then, §9's stop** — the operator chooses again; the distribution name is one constant (`DISTRIBUTION = "agentic-postgres-cli"` in `bin/build-cli.py`). | Says what it is (only the customer CLI) and leaves the product's name free. | **0284** |
| **D2653** | Stage plan `:891-894`: *"Static files built from the repository (a `site/` directory and a build script) and published to Cloudflare Pages"* — the mechanism unnamed. | No workflow publishes anything (`ci.yml` has three jobs and `contents: read`, `:33-34`). A Pages project accepts a *direct upload* (wrangler) or builds from a connected Git repository on Cloudflare's builder. | **The operator, 2026-10-19: CI direct upload.** `.github/workflows/site.yml`: `on: workflow_run: {workflows: [contract], types: [completed], branches: [main]}`; job `deploy` runs only `if: github.event.workflow_run.conclusion == 'success'`, checks out **`github.event.workflow_run.head_sha`**, builds with `bin/build-site.py --out "$RUNNER_TEMP/site"`, and uploads with **wrangler pinned to an exact version** (Run 1 reads it, rig 43c) via `npx --yes wrangler@<x.y.z> pages deploy "$RUNNER_TEMP/site" --project-name agentic-postgres-site --branch main --commit-hash <sha>`; `environment: site` holding the secret `CLOUDFLARE_API_TOKEN` (**Account → Cloudflare Pages → Edit, this account only**) and the variable `CLOUDFLARE_ACCOUNT_ID`; `permissions: contents: read`; actions pinned by SHA like `ci.yml`'s. Sheet C3 (Run 1) creates the token and the environment. | Reproducible from a commit, deployed only after the full check, no token on the VPS or the workstation. | **0283** |
| **D2654** | Stage plan `:889-890`: *"request an invitation (a `mailto:` to the operator's address — no form, no stored personal data, because there is no email system, D1951)"*. | No address is named; no MX record exists on the zone (p5). | **The operator, 2026-10-19: a domain alias.** `invite@agenticpostgresql.com` by **Cloudflare Email Routing**, forward-only to the operator's inbox (Sheet C1, Run 1: the operator enables Email Routing in the dashboard, verifies the destination, adds the rule; the agent reads the MX and TXT records back — DNS-only by construction — and a test mail from another account arrives). The address is ONE constant (`INVITATION_ADDRESS` in `src/agentic_postgres/site_build.py`); the operator's personal address appears nowhere in the tree. **D1951 is unchanged**: the product sends no mail; Email Routing only forwards what a visitor sends. | A published address that is the product's, not a person's; nothing stored, nothing sent. | **0283** |
| **D2655** | Stage plan old text `:955-957`: *"The console: static files under `services/console/`, served by the control project's router, calling `/api/v1` only"*; amended `:913-917`: served from `control.agenticpostgresql.com`. | No static serving exists in `auth-api` (§0); `/` of the control host is Traefik's own 404. The docs container is a first-party fixed-route server with its own CSP (`services/docs/serve.py`); a facility profile starts services on one project only (D2344). `test_no_console_exists_yet` (`test_reality_ledger.py:251-262`) fails the day `services/console/` appears. | **A new image `services/console/`** (`Dockerfile` from `PYTHON_BASE_IMAGE` alone, `serve.py` in `services/docs/serve.py`'s shape, the pages) and **a `console` compose service** (`profiles: [console]`; `mem_limit`/`pids_limit`/`cpus` from `CONSOLE_*` variables rendered like `DOCS_*`; `read_only: true`; uid 65532; network `edge` only; no secret, no mount). **`bin/project-runtime.sh` adds `--profile console` when the render says `APG_CONSOLE=1`**, which `rendering.py` emits beside `AUTH_APP_MODE=control` (`:2239`). **A router `apg-<key>-console`** (`naming.py` derives the name beside `:420-428`) with the rule ``Host(PROJECT_DOMAIN) && (Path(`/`) || Path(`/accept`) || PathPrefix(`/console/`))`` and the baseline chain; `/api/…`, `/docs/…`, `/__apg/…` are untouched. **The serving process never authenticates, never proxies `/api`, holds nothing.** `test_no_console_exists_yet` is **replaced** by Run 5's guard (D2661) under ADR 0280. | The same-origin console the operator decided (D2595) without putting HTML into the API process, with the CSP ours and a route table instead of a file system. | **0280** |
| **D2656** | D2595: *"an `HttpOnly`, `Secure`, `SameSite=Strict` cookie set by the session route for the console, its lifetime the existing session's … every write also checks `Origin` (or a header only the console's own pages send)"*. | Two tokens, not one: a 15-minute JWT and a 30-day single-use refresh token (§0); `_caller` reads only `Authorization`; no cookie, `Origin` or CORS code. | **Cookie mode, selected per request by the header `X-Apg-Console: 1`** (ADR 0281): `POST /v1/sessions` and `POST /v1/sessions/refresh` with the header **set** `__Host-apg_access` (the JWT; `Max-Age` = `expires_at − now`) and `__Host-apg_refresh` (`Max-Age` 2,592,000), both `HttpOnly; Secure; SameSite=Strict; Path=/`, and answer `{"expires_at", "token_use"}` **with no token in the body**; `/refresh` with the header reads the refresh token from the cookie when the body is empty; `DELETE /v1/sessions/current` with the header reads it from the cookie and **clears both** (`Max-Age=0`). **`_caller`**: an `Authorization` header → bearer mode, cookies ignored (unchanged); no header and `__Host-apg_access` present → accepted **only if** `X-Apg-Console: 1` is present **and**, for any method but `GET`/`HEAD`, `Origin` equals `APG_CONSOLE_ORIGIN` exactly; otherwise `401` as today. A cookie value beginning `apg_` is refused (a key never rides a cookie). No CORS is added — the custom header forces a preflight no route answers. | No script can read the session (the page that will hold a database password in Session 44 most of all); a forged cross-site request carries neither the cookie (Strict) nor the header (no CORS). | **0281** |
| **D2657** | D2591 point 3: *"the token shown once to the inviter is printed and displayed as a console URL carrying the token in its fragment (`…/accept#<token>`), so no server, proxy or log ever receives it"*. | The mint answers a bare `invitation_token` (`models.py:569-576`); `org invite --output` writes the token (`cloud.py:485-500`); `read_invitation` requires one whitespace-free token (`:147-151`). No component knows the console's public origin. | **`APG_CONSOLE_ORIGIN`** (`https://<PROJECT_DOMAIN>`, derived by a new `naming.console_origin(project)` and rendered only for the control project, D2655) **is the one source**: the mint answer gains `accept_url = f"{origin}/accept#{token}"` (the token stays its own member); `org invite --output FILE` writes **the link** (still one whitespace-free line, 0600); `read_invitation` accepts either a bare token or a link whose path is `/accept` and whose fragment is the token (anything else refused with the existing message); `accept.html` reads `location.hash`, calls `history.replaceState(null, "", "/accept")` **before its first request**, and posts the token in the JSON body. `Referrer-Policy: no-referrer` (the console's own and the baseline's). **The canary**: a test mints, accepts through the app with `StructuredRequestLog` capturing, and finds the token in no log line (`tests/contract/test_console_session.py::test_no_line_holds_the_invitation_token`). | A fragment is never sent in a request line, a `Referer` or a proxy log; the link is the token's only carrier. | **0282** |
| **D2658** | Stage plan §8 (`:1179`): *"Argon2id for keys and invitations"*. | `one_time_tokens.py:10-20`: an invitation, a refresh token and a key are stored as a **deterministic SHA-256** of a 32-byte random token (ADR 0171: the row is found BY the digest; a KDF buys nothing for a random secret). Argon2id hashes the account's PASSWORD (`control_service.py:498`). | **The tree wins; the stage plan's sentence is wrong and stays as written** (it is a plan of record; this row is its correction). Nothing changes. The link carries the same 43-character token. | Recorded so no run "fixes" a correct digest into a KDF. | 0171 |
| **D2659** | D2591 point 4: *"scan the TOTP QR rendered in the page from the enrolment answer"*; D2596: no third-party script. | The enrolment answer is `{secret, otpauth_uri}` (`control_service.py:387-394`); nothing draws a QR (the operator guide pipes to `qrencode`, `:2113-2115`). Drawing one in the page needs a QR encoder in JavaScript — a vendored third-party script (D2596 refuses it) or one written here (an unreviewed encoder that a phone must read). | **The server draws it.** `FactorEnrolmentResponse` gains **`otpauth_qr`**: an `image/svg+xml` data URI of `otpauth_uri` from **`segno`** (pure Python, BSD-3; **version, licence and the hash read by rig 43b**, added to the auth image's dependency lock the way its other dependencies are — Run 3 reads `services/auth-api/` for the lock file and its regenerating command before touching it). The page shows `<img src="{otpauth_qr}">` (`img-src 'self' data:`) and the base32 `secret` under it, and **drops both from memory once confirmed**. The CLI is unchanged (it may ignore the member). **Rig 43b decodes the SVG with `zbarimg`** (a throwaway Debian container) back to the exact URI — control: a different URI decodes differently; the operator's phone scans one during Sheet W0. | The seed already crosses in this one answer; drawing it there adds no new holder and no script. | **0282** |
| **D2660** | D2591 point 5: *"Connect (the pooled and direct strings, a credential shown once …)"*. | The CLI never sends a database password: credential rotation sends `{"role", "verifier"}` (`cloud.py:1001`) and project creation both verifiers (`:1176-1185`), computed by `scram.verifier` (`scram.py:40-52`: PBKDF2-HMAC-SHA-256, 4,096 iterations, 16-byte salt). | **The console does the same in the browser**: `services/console/scram.js` — the password from `crypto.getRandomValues` (24 bytes, base64url), the verifier with **WebCrypto** (`PBKDF2` 4,096 × SHA-256, `HMAC` `"Client Key"`/`"Server Key"`, `SHA-256`), the format `scram.VERIFIER` accepts. **Proved equal**: `tests/contract/test_console_scram.py` runs `scram.js` in the pinned `NODE_BASE_IMAGE` (Node's WebCrypto) with a fixed password and salt and compares to `scram.verifier(password, salt=…)` — Docker-backed; **rig 43a** shows Chromium's WebCrypto gives the same bytes. The password is held in a closure until the page is left, never in storage, never in a URL. | The control plane keeps holding nothing that opens a project's data (ADR 0246); the browser is the customer's own client. | 0246 |
| **D2661** | Old text `:957-959`: *"the project data views opening that project's Studio forwarders as the member's project identity"*; D2591 point 5 keeps it. | Studio is a loopback process (`bin/studio.py`, ADR 0205: *binds loopback with no alternative*); it is not a container and never published. A hosted Studio would be a second server holding a member's project token. | **No project data view in the console.** A customer reaches their data with their own client (Connect page) and, from Session 44, the SQL editor (D2592). The Ledger `console` row's `stage5_reality` is rewritten in Run 5: *"Static pages served by the control project, calling /api/v1 only: onboarding, projects, connect, branches, backups, usage, insights, monitoring, plan, notifications and settings; no data view and no SQL."* | ADR 0205's boundary is a decision, not a gap; the editor is where browser data access is designed. | 0205 |
| **D2662** | D2591 point 2: *"a curated set (getting started, connecting, branches, backups and restore points, plans and usage, Query Insights and monitoring, the CLI) published by the site; the operator's documents stay in the repository."* | No separate customer pages exist (§0); `managed-projects.md` (42 `bin/` lines, one `sudo`), `control-plane.md` (customer and operator mixed), `monitoring.md` (mixed). | **`site/pages/` is the customer documentation's source**: `index.md` (landing), `quickstart.md`, `pricing.md` (generated body, D2664), `docs/getting-started.md`, `docs/connecting.md`, `docs/branches.md`, `docs/backups.md`, `docs/plans-and-usage.md`, `docs/insights-and-monitoring.md`, `docs/cli.md`, `docs/refusals.md`, `ledger.md` (generated, D2674). Commands are written `apg <family> <verb>` (the packaged command, D2666), never `bin/`. **`docs/managed-projects.md` becomes a pointer** (≤ 20 lines: *the customer documentation is `site/pages/`, published at https://agenticpostgresql.com/docs/*), and the customer halves of `control-plane.md` and `monitoring.md` are cut to a sentence pointing there; their operator halves stay. Every reader of the moved sections is grepped first (D1187: the TEXT as well as the name). **The guard** refuses in any page: `bin/`, `sudo`, `ssh `, `git clone`, `--session`, a `FORBIDDEN_WORDS` member, a Ledger row not `REACHABLE`. | One source for what a stranger reads, checked against the Ledger instead of beside it. | **0283** |
| **D2663** | Stage plan `:891`: *"Static files built from the repository (a `site/` directory and a build script)"*. | No Markdown renderer is in the tree or its lock; ADR 0093: a `bin/` command imports only `agentic_postgres` and `yaml`. | **An in-house Markdown SUBSET** in `src/agentic_postgres/site_build.py`: front matter (`---` YAML with `title`, `ledger: [ids]`, optional `description`), ATX headings `#`–`###` (ids slugged), paragraphs, `-` and `1.` lists (one level), fenced code (```` ``` ```` with an optional language word, HTML-escaped), inline `code`, `**strong**`, `*em*`, `[text](href)` (href relative, `#…`, `https://`, or `mailto:invite@…`), pipe tables (header row + separator). **Anything else is a build error naming the file and line — raw HTML included.** Output escaped by `html.escape`. Deterministic: no timestamp, sorted iteration, `\n` endings. `bin/build-site.py --out DIR [--check]` is the only caller (refuses an `--out` inside the repository; `--check` builds twice into two temporary directories and compares every byte). | A renderer whose whole grammar is in one file and a test, and no dependency to lock. | **0283** |
| **D2664** | Stage plan `:888-889`: *"the pricing page (spec §35's beta sentence and §56's shape, its numbers read from `plans.PLANS` at build time, never typed)"*. | `PLANS` holds entitlements (value, unit, enforced, reader) and statuses; **no price, no currency** (§0). The spec is not in the repository. `billing` is `not_offered` (*"The beta is free and takes no payment details."*). | **The pricing page is the two plans' entitlements, generated**: a table per plan from `plans.PLANS[name].entitlements` (each value and unit; `enforced` shown as *"enforced"* / *"shown, not enforced"*; a `tuple` value joined), the plan's status in words (`active` → *"Every organisation has it"*; `unavailable_during_beta` → *"Not available during the beta — Notify me in the console"*), and `plans.BETA_SENTENCE` verbatim. **No price, no currency sign, no "per month" appears** (a guard scans the built page for `$`, `€`, `£`, `/mo`, `per month`). A test changes a value in a copy of `PLANS` (monkeypatch) and finds the page changed. | A number the reader can trust is one the product enforces or shows from one table. | **0283** |
| **D2665** | D2592: *"The Ledger schema's `target_session` maximum (43) widens to 45 in the first session that targets a row past 43"*; the site's claims come from the Ledger. | `console` `planned` → 43; `sql_editor` `not_offered`, `null` (`:944-957`; Session 42's D2592 cites `:844-857`, stale); schema max 43 (`:121-128`). **`management_api.customer_text` still says** *"Creating a project is not available yet and says so"* (`:151-153`) while `projects_self_service` is `beta`; **`cli_remote.today`** says *"Five commands in the checkout's bin/"* (`:172-194`). | **Run 9 (the bump)**: `console` → `trial` naming only Session 43's claims (ADR 0261); `sql_editor` → `planned`, `target_session: 44`, `customer_text: "Not open yet."` (the operator's D2592); the schema's maximum → **45**; `management_api.customer_text` and `cli_remote.today`/`customer_text` rewritten to what the tree does (`cli_remote`'s evidence gains `cli_package`). **Run 11 (the close)**: `console` → `beta` if its claims passed. | The site prints `customer_text`; a stale sentence there is a false claim on a public page. | 0254, 0261 |
| **D2666** | D2594: *"A distribution holding only the customer families (no server code, no operator command), its version the product's `template_version`, installed by `uv tool install <name>` or `pipx install <name>`"*. | `bin/cloud.py` imports `control_client`, `scram` (stdlib only) and **`plans`** — through `service_source` and `REPO_ROOT`, which no wheel can carry (§0); `INTEREST_PLANS` is its only use (`:1297-1298`). The root `pyproject.toml` describes the repository, not a CLI. The tests load `cloud.py` by path (`test_control_cli.py:971-974`). | **One source, staged at build time** (ADR 0284): `bin/cloud.py`'s import block `:82-88` is wrapped in two marker comments (`# packaging seam: begin` / `# packaging seam: end`); **`plans` leaves it** — `plan notify-me` reads `GET /v1/plans` and refuses locally a name that is absent or `active` with today's message (`INTEREST_PLANS` removed; its test re-pointed, D1119). `bin/build-cli.py --out DIR` stages `apg_cli/__init__.py` (`__version__` = `VERSION`), `apg_cli/__main__.py`, `apg_cli/cli.py` (= `bin/cloud.py` with the seam replaced by `from apg_cli import control_client as cc`, `from apg_cli import scram`, `from apg_cli.control_client import ClientError`), `apg_cli/control_client.py` and `apg_cli/scram.py` (byte-equal copies), and a generated `pyproject.toml` (`name = "agentic-postgres-cli"`, `version`, `requires-python = ">=3.10"` **only if rig 43d shows the code runs on 3.10**, else `">=3.12"`, no dependencies, `[project.scripts] apg = "apg_cli.cli:main"`, a README and the repository's licence), then runs `uv build --wheel --sdist --out-dir DIR/dist` on the staged tree. `cloud.py` gains `--version`. **Guards**: the staged tree differs from its sources only inside the seam; every `import` in it is stdlib or `apg_cli`; the wheel installed into a clean `python:3.12` container with **no network** runs `apg --version` and every family's `--help`. Nothing staged is committed (`--out` outside the tree, refused otherwise). | A customer installs a CLI without a clone, and the CLI the repository's own tests exercise is the one that ships. | **0284** |
| **D2667** | D2594: *"published by a GitHub Actions job using PyPI trusted publishing … only from a tagged commit whose CI passed."* | `ci.yml` has no tag trigger and no `id-token` (§0). Release tags are bare versions (`1.20.0` on `77303e4`), pushed from the workstation (D2041). | **`.github/workflows/publish-cli.yml`**: `on: push: tags: ['[0-9]+.[0-9]+.[0-9]+']`; `permissions: {}` at the top; job **`verify`** (`permissions: actions: read, contents: read`) reads `gh api repos/${{ github.repository }}/actions/runs?head_sha=${{ github.sha }}&event=push&branch=main` and **passes only if a `contract` run for that SHA concluded `success`** — empty list or any other conclusion fails (D1057's three buckets); the tag must equal `VERSION` at that commit; job **`build`** (`needs: verify`) runs `bin/build-cli.py --out "$RUNNER_TEMP/cli"` and uploads `dist/` as an artifact; job **`publish`** (`needs: build`, `environment: pypi`, `permissions: id-token: write`) downloads it and runs **`pypa/gh-action-pypi-publish` pinned by commit SHA** (Run 1 reads the release and its SHA, rig 43d). **The first publish is Session 43's tag** (Run 10). | The release tag is the one event that can publish, and only a green commit carries one. | **0284** |
| **D2668** | Stage plan *Measures (added)* `:947-948`: *"the path from an invitation link to a working connection string, timed through a real browser (the plan decides how it drives one)"*. | No browser automation in the tree; the external proofs read records written by instruments (`APG_LIFECYCLE_RECORD_FILE` pattern; the roster `tests/conftest.py:86-225`). | **Playwright for Python in its official image, pinned by digest** (`mcr.microsoft.com/playwright/python:v<x.y.z>-noble@sha256:…`; rig 43e reads the newest release ≥ 14 days old, its digest, that the `playwright` package and Chromium are inside, and that `performance.getEntriesByType('paint')` answers). **The driver `tests/external/browser/console_walk.py`** runs inside it (the checkout mounted read-only, the record directory mounted read-write, `--network host`), drives the console and writes **one record** (JSON, 0600; each step's name, outcome, start/end monotonic times, the first paint, the headers read; **no secret value** — the password and the TOTP seed live in variables only, D2416). **The external proofs** `tests/external/test_session43_console.py` read it through **a new environment gate `APG_CONSOLE_RECORD_FILE`** (added to the roster `tests/conftest.py:86-225`, exported by `bin/session-43-check.sh --console-record-file FILE` in external mode — one flag added, unlike D2588). Rejected: driving the operator's own browser (not reproducible, not evidence); Selenium (a second driver to pin). | A browser in a pinned image is a measurement anyone can repeat; a record read by proofs is the shape the evidence already trusts. | 0280 |
| **D2669** | Stage plan `:925-927`: *"The target, measured by Session 45's walk: a stranger holding an invitation link reaches a working connection string in the browser, with no terminal."* Session 43's *Measures* time the same path. | `slot1-` … `slot6-prod` are consumed; no slot is free (a create answers `capacity_exhausted {no_slot}`). The probe organisation `probe-s37` holds `slot3-prod` (the kept customer project; its passwords in WSL `~/s39/run11/creds/slot3-prod/`, 0700/0600). Admins need TOTP (`control_roles.py:264-273`). | **Session 43's walk uses `slot3-prod`, not a new slot**: the probe owner (`~/s37/probe.json`) mints a **membership invitation, role `admin`**, by `apg org invite --role admin --output F` (the link); the driver opens the link, creates the account (`walk-s43-<6 hex>`), enrols TOTP from the page (reads the base32 under the QR, computes the code with stdlib `hmac`), confirms, logs in with the code, opens `slot3-prod`'s **Connect** page, **rotates `customer_app` from the page** (verifier only, D2660), waits for the operation, reads the pooled string with the password shown once, and reloads to see it gone. The instrument (`~/s43/run10/s43-walk.sh`) then **copies the old creds file to `.before-s43` and writes the new password into `~/s39/run11/creds/slot3-prod/`** (0600, the file name read from the directory first), and the external proof connects with it over TLS (`sslmode=verify-full`) and runs `SELECT 1`. **Afterwards the probe owner removes the walker's membership** (`apg org remove`); the account remains (D2065). A stranger's ACCOUNT invitation that creates an organisation and a project is **Session 45's**, on `slot7-prod` (D2593). | The browser path is proved end to end on a live project without consuming a slot; the account path differs only in two routes already proved by the CLI. | — |
| **D2670** | Scope closure §35 *inherits* 2: *"D2636, D2637, D2642 — small, and each a redeploy of all four when it lands."* | §0: the three sites. | **Run 2, each with a failing test first.** **D2636**: Run 2 first reproduces with the pinned collector image (`docker run -d --name s43-nohc <OTEL_COLLECTOR_IMAGE>` then the template) and reads which construct survives a missing `Health` (`{{with .State.Health}}{{.Status}}{{else}}none{{end}}` and `{{if index .State "Health"}}` are the candidates — measured, the first that prints `none` with rc 0 is used); a Docker-backed test `tests/contract/test_telemetry_status.py` inspects a container with no healthcheck (control: one with). **D2637**: the check loops over the same `libexec/agentic-postgres-*` glob the install reads (one function both call); test with a temporary `libexec` holding a seventh launcher → `--check` names it. **D2642**: the count is `len(created)` of the resources `--apply` created (the variable read from `:990-1027` before editing); a test with a fake provider plan of 17. | Each was deferred only because the tag was cut; this session redeploys all four anyway. | — |
| **D2671** | Stage plan §7 row 43: *"Ends on a host? Yes — the console on the host; the site on Cloudflare Pages."* | A new commit's deploy recreates `auth`, `mcp`, `storage` (~8–14 s, D2034); a new service under a profile starts on the project that enables it; Traefik reads a container's labels from the Docker provider (no edge recreate). No unit, launcher, `postgres` command or migration changes in this session. | **One sitting** (Run 10): R1 (`upgrade plan` reads the price), **R2a–R2d** (beta, alpha, `slot3-prod` by `slot.sh redeploy`, **control-prod last** — the console appears with it), A1, RA, K1, V1, X0, W0 (the walk's dry run), **W1 (the walk)**, S1 (the sweep), the external half, the merge, the tag. **No reboot** (nothing a boot would read changed — D2558's repair was proved at Session 42's B1), **no slot**, **no database restart**. The windows are probed as Session 42's (`s43-window.py` derived from `~/s42/run8/s42-window.py`). | The smallest trip that proves a release of four and a browser path on the live host. | — |
| **D2672** | D2591 (`session-42…:476`): *"README's setup clones and runs `uv`/`pip -r requirements-dev.txt`, `:242-250`"*. | `README.md` has **no** `git clone` line and no GitHub URL; its setup is `## Local bootstrap` `:225-265`. | **Recorded; nothing to change in the README for this.** The quickstart (D2662) says `pipx install agentic-postgres-cli` (or `uv tool install`) and never a clone. | A row that described the tree wrongly is corrected where it is next read. | — |
| **D2673** | Stage plan §11 (`:1301-1318`): the `THR-*` rows first. | The hosted list numbers **13 twice** (`threat-model.md:338`, `:354`). | **Run 1 appends items 16–20** (§5 Run 1) and **leaves the duplicate as it is** — renumbering would move every citation of items 13–15 in thirteen plans. Recorded so the next list is numbered from 16. | A numbering slip is cheaper to note than to move. | — |
| **D2674** | Old text `:957-958`: *"the beta sentence and the Ledger served from `/api/v1/ledger`"*. | No such route (`control-plane.md:310`); the services cannot read the YAML (`operations.py:28`). | **The Ledger is a page of the site** (`ledger.md`, generated at build from `reality_ledger.load()`: every row's `concept`, status in words, `customer_text`), and the console links to it. **No new route.** The beta sentence is already served as `note` by `GET /v1/plans` (`control_service.py:845, 862`) and printed by the pricing page from the same constant. | A public page needs no API; one more route would be one more reader of a file the services cannot read. | **0283** |
| **D2675** | *Measures (added)* `:946`: *"The console's first paint against the host"*. | Nothing measures a page. | **The driver records** `performance.getEntriesByName('first-contentful-paint')[0].startTime` and `domContentLoadedEventEnd` for `/console/` (cold: a new browser context) **three times**, and the link → string duration (from `page.goto(link)` to the password visible). Run 11 writes them to `capacity.ENVELOPE`'s Session 43 section, **named as from the operator's workstation over its own network** — not a property of the host alone. | A number with its vantage point named. | — |
| **D2676** | Rig needed before any site run. | No Pages project of this product exists (p7). Pages' handling of `_headers` (CSP), `_redirects` and a missing path is Cloudflare's behaviour, not ours. | **Rig 43c (Run 1)**: the agent creates a throwaway Pages project `apg-rig-43c` through the API, uploads a three-file site with a `_headers` file (`/* Content-Security-Policy: default-src 'none'`) and a `404.html` by **wrangler in the pinned Node image** with a **temporary token the operator creates for the rig and revokes after**, reads `curl -sI` of `/`, `/a/` and `/missing` on `apg-rig-43c.pages.dev` — the CSP present on all three (control: a path the `_headers` rule does not match carries none), `/missing` → 404 with `404.html`; then **deletes the project** and reads it gone. The production project `agentic-postgres-site` is created in Run 7 (Sheet C4). | A header the site's safety rests on is read from Cloudflare's answer, not its documentation. | 0283 |
| **D2677** | Stage plan §10 (`:1282-1284`): each session's gate *"derived by diff from the newest … header and usage block rewritten whole"*. | Session 42's gate added no flag (D2588). Session 43 adds one environment gate (D2668). | **`bin/session-43-check.sh` derived from 42's by diff**; header and usage rewritten whole (D1488); **one flag added**: `--console-record-file FILE` (external mode only; exported as `APG_CONSOLE_RECORD_FILE`; refused in other modes with the gate's existing usage error). The offline mode gains nothing: the site's and the CLI's builds run inside their contract tests (Docker-backed where needed). `tests/contract/test_session_forty_three_gate_modes.py` derived from 42's. | The gate's surface grows by exactly the one input the new proofs read. | — |
| **D2678** | D2595: *"No script on the page can read the session."* | The edge's access log drops `Authorization` and `Cookie` (`traefik.yaml:155-159`); the docs server logs only method, path, status (`serve.py:143-150`); `StructuredRequestLog` logs `request_id, method, route, status, elapsed_ms` (ADR 0249). | **Kept by construction and proved**: the console server's `log_message` copies `serve.py`'s (path without query); `tests/contract/test_console_session.py::test_no_line_holds_a_cookie_value` sends a request with both cookies through the app and finds neither value in any captured line. | A session that no script can read must not be readable in a log either. | 0281 |
| **D2679** | — (carried) | `/v1/sessions` and `/v1/invitations/accept` are unthrottled by decision (D2166; `control-plane.md:308-311`); the edge's `apg-rate-limit` (20/s average, burst 40, per source) is the only limit. The site will link the console publicly for the first time. | **Unchanged in this session; named in §10 and in THR-CON-GUESS** (Run 1): a guess against a password is Argon2id's cost plus the edge limit; a guess against a TOTP code is 10⁶ per window. A throttle is an operator decision, not this plan's. | A public link changes who can reach a door, not what the door is. | 0252 |

**Rows added by the runs** (from **D2680**, in execution order):

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2680** | Rigs 43b/43c and D2660: *"the digest `versions.env` pins as `PYTHON_BASE_IMAGE`"*, *"the pinned Node image (`NODE_BASE_IMAGE`)"*. | `versions.env` pins **`PYTHON_RUNTIME_IMAGE`** (`python:3.12-slim@sha256:229a2c5b…`, `:24`) and **`NODE_RUNTIME_IMAGE`** (`node:22-alpine@sha256:c610fcdf…`, `:18`). `PYTHON_BASE_IMAGE`/`NODE_BASE_IMAGE` are the BUILD ARGUMENTS `services/docs/Dockerfile:16-17` declares, which `compose.yaml` fills from the two `*_RUNTIME_IMAGE` pins. | **The rigs used the `*_RUNTIME_IMAGE` pins**; `services/console/Dockerfile` declares `ARG PYTHON_BASE_IMAGE` filled by compose exactly as `docs:` is; a test that needs "the pinned Node image" reads `NODE_RUNTIME_IMAGE`. | The plan named the argument, the tree pins the variable; one source either way. | 0280 |
| **D2681** | Run 1 Step 4: *"The `THR-*` table gains five rows … and one carried row `THR-CON-GUESS`"*. | A table row must name requirements that EXIST in the registry and node ids that COLLECT (`tests/contract/test_acceptance_registry.py:482-505`: `test_threat_model_node_ids_are_collectible`, `test_threat_model_requirement_ids_exist_in_the_registry`); the requirements are registered in Run 9. The hosted list's own preamble says *"Each item moves into the table … in the run that registers the requirement"* (`threat-model.md:186-196`). | **Run 1 wrote hosted-list items 16–21** (the five plus the carried guessing item); **Run 9 moves each into the table** as `THR-CON-XSS`, `THR-CON-CSRF`, `THR-CON-LINK`, `THR-SITE-CLAIM`, `THR-SUPPLY`, `THR-CON-GUESS` with its registered requirement. `THR-CON-GUESS` needs a requirement Run 9 names (no new control: `CON-CSRF-001` or `CON-SESSION-001` is the nearest; Run 9 decides). | A row with an unregistered requirement is a control that looks measured — the preamble's own rule. | 0280–0284 |
| **D2682** | D2659: *"`segno.make(uri, error="m").svg_data_uri(scale=4)`"*; rig 43b: *"Read that the data URI contains no `http` and no `<script`"*. | Rig 43b: the default SVG is dark modules on a **transparent** background — `zbarimg` decodes it to **nothing** after `rsvg-convert`; with `-b white` it decodes exactly (control: a one-character-different URI decodes to itself). **`svg_data_uri(scale=4, light="white")` decodes exactly with no rasteriser help; the default does not** (the control). The data URI holds `http` ONLY as the SVG namespace `xmlns='http://www.w3.org/2000/svg'`; no `href`, no `<script`. | **Run 3 calls `svg_data_uri(scale=4, light="white")`.** `test_the_qr_references_nothing` asserts no `<script`, no `href`, and that the only `http` in the decoded SVG is the namespace URI — not "no `http`". | A QR that a dark page makes unreadable is a step people fail; a test that forbade the namespace would fail on the first run. | 0282 |
| **D2683** | D2666: *"`requires-python = ">=3.10"` only if rig 43d shows the code runs on 3.10, else `">=3.12"`"*. | Rig 43d: the wheel installed offline runs `apg --help` byte-equal to the tree's usage on **3.12 and 3.11**; **3.10 fails at import** (`from datetime import UTC` — 3.11+, `bin/cloud.py:78`). | **`requires-python = ">=3.11"`** — the rig's own rule, *"the lowest that passes decides"*; D2666's two-way choice omitted 3.11. | The honest floor is the lowest measured version that runs. | 0284 |
| **D2684** | D2666: *"the wheel … runs `apg --version` and every family's `--help`"*; rig 43d's control: *"`bin/cloud.py --help` from the tree prints the same usage text"*. | `bin/cloud.py:1509` `argparse.ArgumentParser(prog="cloud.py", add_help=False)`: the packaged command prints **`usage: cloud.py`**, and **`--help` exits 2 as a usage error** — in the tree (the control: rc 2) and in the wheel alike (rig 43d: rc 2, byte-equal output). Family parsers behave the same (`login --help` → rc 2, *"the following arguments are required: verb"*). | **Run 6**: `prog` is the invoked name's basename (`cloud.py` from the tree, `apg` from the package); `--version` added. Whether `--help` becomes a real help (exit 0) is Run 6's to decide by reading the shims' and `test_control_cli`'s expectations first; **`test_the_wheel_runs_every_family` compares the wheel's output and exit code to the tree's**, whatever they are, never asserts 0 blind. | A packaged command that names a file the customer never saw; a proof asserting exit 0 would fail on first run. | 0284 |
| **D2685** | §9: *"the repository has no licence file when Run 6 stages the package (a public distribution needs the operator's licence decision)"*. | No `LICENSE*`/`COPYING*` in the tree; the GitHub repository is **public** with `license: null` (read 2026-10-19). | **The operator, 2026-10-19: Apache-2.0** for the CLI distribution and the repository. **Run 6** adds `LICENSE` (the Apache License 2.0 text, unmodified) at the root, `license = "Apache-2.0"` in the staged `pyproject.toml`, and the file in the wheel and sdist (not added in Run 1: Run 1 runs no test, and a new root file is read by repository guards). The stop is cleared. | The decision is the operator's; the file lands with the tests that read it. | 0284 |
| **D2686** | D2668: *"rig 43e reads … that the `playwright` package and Chromium are inside"*. | Rig 43e: `mcr.microsoft.com/playwright/python:v1.63.0-noble@sha256:72bd171a…` (1,013,940,272 bytes) holds Python 3.12.3 and the browsers (`chromium-1243`, `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`) but **NOT the `playwright` package** (`ModuleNotFoundError`), and no `ensurepip` (a venv fails). `pip install --target DIR playwright==1.63.0` (+ `greenlet` 3.5.6, `pyee` 13.0.1, `typing_extensions` 4.16.0) then runs Chromium 153.0.8010.12 headless; FCP recorded (control: `about:blank` has none). | **Run 8's instrument installs the package into a target directory from a hash-locked requirements file** (`tests/external/browser/requirements.txt`, `--require-hashes`, the four pins above, hashes read from PyPI) with network, then runs the driver with `PYTHONPATH` set. The image stays pinned by its index digest. | The image is the browsers; the package is ours to pin. | 0280 |
| **D2687** | Rig 43c (D2676): *"reads … whether Pages adds headers of its own (recorded whole)"*; §9: *"rig 43c: Pages does not apply `_headers` to the HTML pages, or adds a script or a third-party request of its own"*. | Rig 43c (settled reads, two rounds): `_headers` applies to every HTML answer, `/missing` included (404 with `404.html`); `Referrer-Policy` in `_headers` REPLACES Pages' default `strict-origin-when-cross-origin`; `! Access-Control-Allow-Origin` DETACHES Pages' default `*`; no `<script` in any body. Pages/Cloudflare ADD `x-content-type-options: nosniff`, `cache-control`, `etag` and **NEL** (`report-to` → `https://a.nel.cloudflare.com/report/v4?s=…`, `nel` `success_fraction` 0.0) — and **`! Report-To` / `! NEL` do NOT detach them** (a fourth pass). Reads in the first ~20 s after a deploy return 522s mixed with 200s. Also: the operator's first temporary token held Pages **Read** (GET answered 8000007, create answered `10000 Authentication error`); edited to Edit, it worked. | **Not §9's stop (the agent's ruling, told to the operator)**: NEL is no script and causes no request by the page; the browser reports failed fetches only, to the CDN serving every byte. Recorded in ADR 0283; **Sheet C4 (Run 7) reads the headers on the custom domain** (the zone's own NEL setting may differ). The site's `_headers` carries `Referrer-Policy: no-referrer` and `! Access-Control-Allow-Origin`; the build refuses a site with no `404.html`; **every live read (Sheet C4, `SITE-LIVE-001`) waits for five consecutive 200s** before reading. Sheet C3's token wording stays (`Edit`); the rig token's `Read` was a slip at creation. | What Cloudflare adds is a fact of the platform to be named, not hidden; a read before propagation is not a reading. | 0283 |
| **D2688** | D2670 (D2636): *"the inspect template already carries `{{if .State.Health}}` and still exits 1 … candidates `{{with .State.Health}}…` and `{{if index .State "Health"}}`"*. | Run 2 (`~/s43/run2/d2636.txt`, Docker 29.5.2, the pinned collector image): the SHORT template `{{.Name}} health={{if .State.Health}}…` prints `none` rc 0; the FULL `do_status` template fails *map has no entry for key "Health"*. **The cause is `{{.HostConfig.NanoCpus}}`**: the CLI runs an inspect template on its typed struct first (field `NanoCPUs`) and falls back to the raw JSON map only when that fails — and in the map a missing key is an error. Control: short + `NanoCpus` fails, short + `NanoCPUs` passes. In the full template `with .State.Health` fails too; `if index .State "Health"` and `with index …` print `none` rc 0 and the status of a container that has one. | **`{{if index .State "Health"}}`** (the plan's rule: the first candidate that prints `none` with rc 0), which reads in either mode; `NanoCpus` kept (it is what the map holds, and what the host's lines have always said). Commented at the template. | A template that fails only beside an unrelated field looks intermittent from outside; the mechanism is what keeps the next one from regressing. | — |
| **D2689** | D2670 (D2642): *"the count is `len(created)` of the resources `--apply` created (the variable read from `:990-1027`)"*. | No such variable: `apply()` keeps `created_so_far` (project and identity only, for the failure report) and ignores `create_secret`'s return, which `add_missing_secrets` reads as *created vs already present* (`:788-810`). The plan counts project + identity + client secret + one value per generated secret + the read-only GRANT (`describe_plan`, `:680-686`). | **`resources_created`**: 3 (project, identity, client secret) + one per `create_secret` that returned True; the grant is a permission, not a resource. Session 42's plan of 17 is 16 resources. `created_so_far` (the failure report) unchanged. Test reads the expected number from what the fake provider RECORDED, at sessions 2 and 42 (control: their contracts differ in size, so no literal passes both). | The count is a reading of what this run did, not of the plan. | — |
| **D2690** | Run 3 step 4: *"`segno` joins `requirements-dev.in` … and `bin/lock-dev-deps.sh --update` relocks `requirements-dev.txt`"*. | `--update` resolves **as of now** and stamps a new cutoff (`bin/lock-dev-deps.sh:176-190`): every floating dev dependency (pytest, httpx, jsonschema …) would move inside a run about cookies — D238's coupling, in the dev lock. The committed cutoff is `2026-09-03T15:16:21Z`; segno 1.6.6 (2025-03-12) predates it. | **Locked AT THE COMMITTED CUTOFF** with the script's own `compile_to` and `stamp` (sourced, `main` removed; `~/s43/run3` / `/tmp/s43-devlock.sh`): the diff is exactly `segno==1.6.6` with the two hashes rig 43b read (wheel `28c7d081…`, sdist `e60933af…`); `--check` and `--check-environment` pass (99 pinned). `versions.env` by `lock-versions.sh --update --packages-only` (no image moved). | Adding one package is not the moment to move the world. | 0282 |
| **D2691** | Run 3 step 1: *"the control-mode setting `console_origin` reads it (required in control mode … a control app with no origin refuses to start)"*. | `test_the_control_mode_reads_exactly_what_auth_reads` holds `load(mode="control") == load(mode="auth")` (one environment, two modes, ADR 0251), and `bin/app-contract.py:201` builds `create_app("control").openapi()` with NO environment — the first build-time read made the snapshot capture fail (the run's first `--update` raised `APG_CONSOLE_ORIGIN is required`). | **Beside `Settings`, not in it**: `settings.CONSOLE_ORIGIN_VARIABLE` + `load_console_origin()` (an https origin, no path — compared byte for byte with `Origin`), read FIRST in the lifespan in control mode (`app.state.console_origin`), never at build. Both compose guards widen by that one named constant, `auth` only (`APP_MODE`/`APG_OTLP_LOGS_ENDPOINT`'s precedent). Rendered `APG_CONSOLE` (`1`/`0`) and `APG_CONSOLE_ORIGIN` (`https://<domain>` / empty) for every project; compose passes `${APG_CONSOLE_ORIGIN?required}` — set, possibly empty (the plan's `:-` failed `test_every_setting_is_required_interpolation_or_a_literal`: no default in `auth`'s environment; `STORAGE_CORS_ALLOWED_ORIGINS`'s shape instead). The rendered-mode test reads the two with `.get` (D2381). | A document generator must not need a running deployment's settings; the guard that the two modes read one environment stands. | 0281 |
| **D2692** | Run 3 step 6: *"the QR decoded structurally (an `image/svg+xml;base64,` prefix, `<svg` after decoding, no `http`, no `<script`)"*. | segno's `svg_data_uri` is **percent-encoded**, `data:image/svg+xml;charset=utf-8,%3Csvg…`, not base64; its only `http` is the namespace (D2682). | The test asserts the prefix segno produces, decodes by `urllib.parse.unquote`, and asserts no `<script`, `href` or `url(`, one `http` = the namespace, and `fill='#fff'` (the white background). | Assert what the library emits, read once, not what was guessed. | 0282 |
| **D2693** | Run 3 step 2: *"`_caller`: `Authorization` present → today's path; else … cookie"*. | A second reader of the bearer: `accept_invitation` decided "signed in" by `request.headers.get("authorization")` (`control_routes.py:404`) — a console user accepting a membership would have been anonymous. | **One rule, `_bearer(request)`**, read by `_caller` AND by `accept_invitation`: `Authorization` wins; else the access cookie only with the header (and, for a non-read, the console's `Origin`); a cookie value starting `apg_` is a 401. | CLAUDE.md §7 question 5: when a decision is implemented, every caller gets it. | 0281 |
| **D2694** | ADR 0281: *"A write's Origin check also applies to the three session routes in console mode"*; `DELETE /v1/sessions/current`'s description: *"Answers 204 whether or not the token named a live session."* | — | **In console mode (the header present) a login, refresh or logout from any other `Origin` is `401` before its body is read** — the logout's *"always 204"* holds for bearer mode and for the console's own origin. In console mode an empty body reads the refresh cookie; a logout with no cookie and no body ends nothing and still clears both cookies (204). | A cross-origin request carrying the console's header is not the console. | 0281 |
| **D2695** | Run 3 step 3: *"`org invite --output` writes `accept_url`"*. | Until 1.21.0 is deployed, the hosted control plane (1.20.0) answers no `accept_url`. | `org invite` writes `accept_url` when the server answers one, else the bare token, and says which (*"the invitation link written to …"* / *"the invitation token written to …"*); `login accept` reads either. | The CLI from this checkout keeps working against the deployed release until the sitting. | 0282 |
| **D2696** | Run 4 step 4: *"no string matching `\b(select\|insert\|update\|delete\|create\|drop\|alter)\s` case-insensitively outside comments — `test_no_script_holds_sql`"*. | That pattern matches the onboarding page's own sentence *"Create your account"* (and Run 5's *"Create organisation"*, *"Delete project"*). | **The guard matches SQL's SHAPE** (`select … from`, `insert into`, `update … set`, `delete from`, `create/drop/alter table\|role\|schema…`), with a control in the same test: SQL text is recognised, the pages' words are not. Comments are full-line `//` only (asserted) and removed before every scan. | A guard that fires on the product's own words gets switched off; one shaped like what it forbids does not. | 0280 |
| **D2697** | Run 4 step 1: the routes are the seven files, `REDIRECTS`, `HEALTH_PATH`. | The pages call `/api/v1`, which is `identity.route_control_path` — `{api.public_base_path}/v1`, a manifest value. A page that typed it would be a second derivation (ADR 0061). | **One more answer, not a file: `/console/env.json`** → `{"api": "<APG_CONSOLE_API_PATH>"}`, compose passing `${CONTROL_ROUTE_PATH:?required}`; `api.js` reads it once. Without the variable the answer is 503, never a guessed path. | The renderer stays the one authority for a path. | 0280 |
| **D2698** | D2660: *"the password from `crypto.getRandomValues` (24 bytes, base64url)"*. | The CLI's every database password is `secrets.token_urlsafe(32)` (`bin/cloud.py:1031, 1206`): 32 bytes. | **`scram.js` uses 32 bytes** (`PASSWORD_BYTES = 32`, base64url unpadded), the CLI's rule. | One rule for a customer's password, wherever it is made. | 0280 |
| **D2699** | Run 4 step 2: *"`cpus` "0.25" (the docs service's value if lower — read it)"*; limits from a measurement. | Measured (`~/s43/run4/measure.txt`): 1,008 requests over every route, `memory.peak` 46,206,976 B (44.07 MiB), `pids.peak` 8, healthy; docs' `cpus` is 1.0 (not lower). Four counting guards in `test_process_limits.py` moved with the new service: services 22 → 23, long-running 11 → 12, the memory set + `console`, and `test_cpus_is_two_for_postgres_and_one_for_every_sidecar` (`console` 0.25, named). | **192 MiB / 64 pids / 0.25 cpu** in `config.SERVICE_MEMORY_LIMITS_MB` and `SERVICE_RESOURCE_DEFAULTS`, rendered as `CONSOLE_*`; the four guards widened to the measured set (each a named member, ADR 0280); `test_the_console_is_bounded` new. | ADR 0244's rule applied to a measurement, not a guess. | 0280, 0244 |
| **D2700** | ADR 0280: *"the exact CSP and security headers on every answer (404 and redirect included)"*. | Measured (`~/s43/run4/docs501.txt`): `services/docs/serve.py`'s 501 for another verb (the base handler's `send_error`) carries **no** CSP; its 404 does (control). | **The console adds its headers in `end_headers`**, so its 501 carries them (`test_every_answer_carries_the_policy` asks a 501). The docs server is left as it is — its own surface, a later session's (§10). | The console's whole safety is its policy; an answer without it is one that opted out. | 0280 |
| **D2701** | Run 4 step 1: `REDIRECTS = {"/": "/console/", "/console": "/console/"}`; the router rule ``Path(`/`) \|\| Path(`/accept`) \|\| PathPrefix(`/console/`)``. | `/console` (no slash) is not in the rule, so through the edge it is Traefik's own 404; the server's redirect for it is reachable only inside the container. | **Kept as planned** (§9's stop names any path outside the three, and adding `Path(`/console`)` would be a fourth); the redirect is harmless and costs nothing. | Recorded so nobody reads the redirect as a published path. | 0280 |
| **D2702** | Run 5's table: *"Create organisation / project `#/new` — `POST /v1/organizations`, `POST /v1/projects` (both verifiers from `scram.js`; the two passwords shown once)"*; §0: *"`project create` builds both customer verifiers `:1176-1185`"*. | `CreateProjectRequest` is `{organization, name, profile, admin_username, handoff_sha256}` — no verifier. `bin/cloud.py:650-733`: the CLI keeps a HANDOFF TOKEN through the 20+ minute creation and then CLAIMS the project's application administrator by presenting it to the **new project's own** `{app_route}/auth/reset-password` — another origin from the console, and a token that would have to outlive a reload with no storage allowed (ADR 0280). The two verifiers at `:1180-1230` are **branch** creation's. | **The operator, 2026-10-20: the console creates organisations only; a project is created with `apg project create` / `claim` in Session 43** (the overview says so, and the Ledger's `console` row). Browser creation and claim are designed in Session 44/45's plan — Session 45's walk needs it (D2669). | A claim from the console is a cross-origin door this plan did not price; the smallest honest console offers what it can finish. | 0280 |
| **D2703** | — | The Ledger's `agents`, `workflows`, `connectors` and `audit` rows said *"the console reaches them through Studio forwarders"*; D2661 decided no data view in the console. | **Rewritten**: each is reached at the project's own address; *"the console has no data view (D2661)"*. | A `stage5_reality` sentence the site will print must not promise what the console decided against. | 0280 |
| **D2704** | D2666: *"`cli.py` (= `bin/cloud.py` with the seam replaced by [three imports])"*; Run 6 step 1: `--version` reads `VERSION` inside the seam. | Beyond the imports, two things in `cloud.py` must differ in a package: the program name in usage lines (`prog="cloud.py"`, D2684) and ten hints that name `bin/<family>.sh` (`:220, 229, 305, 410, 421, 440, 610, 646, 686, 896`) — a `pip install` user has no `bin/`. `argv[0]` would read `__main__.py` under `python -m`. | **The seam carries four values**: the imports, `__version__` (the checkout's `VERSION` / the package's), `PROG` (`cloud.py` / `apg`) and `COMMAND` (`bin/{}.sh` / `apg {}`); the ten hints read `COMMAND.format(family)` (the tree prints exactly what it printed). `--version` → `apg <VERSION>`, exit 0 (`main` now returns 0 for argparse's own exit 0). `--help` keeps the tree's behaviour (exit 2, usage — `logout` has no verbs, so its is the top level's); `test_the_wheel_runs_every_family` compares the wheel's words and exit to the tree's, whitespace collapsed (argparse indents by the name's length). | The package must not tell a customer to run a file they do not have. | 0284 |
| **D2705** | Run 6 step 2: `DIR/README.md` from `site/pages/docs/cli.md` *"or a fixed paragraph and the site's URL if Run 7 has not landed; the run says which"*; `license` per ADR 0284. | Run 7 has not landed. The root `pyproject.toml` requires `setuptools>=68`; an SPDX string `license = "Apache-2.0"` needs setuptools 77+. `uv build` also writes a `.gitignore` into the out-dir. | **A fixed README paragraph** naming https://agenticpostgresql.com/docs/cli/; `license = { text = "Apache-2.0" }` plus the OSI classifier and `license-files = ["LICENSE"]` (the wheel's METADATA reads `License: Apache-2.0`, `License-File: LICENSE`, `Requires-Python: >=3.11`); `build-cli` removes the `.gitignore` and refuses unless `dist/` holds exactly one wheel and one sdist. | The backend the repository already names, and a `dist/` the publish job can upload whole. | 0284 |
| **D2706** | Run 6 step 3: *"every action pinned by commit SHA as `ci.yml` pins its own (copy those SHAs for checkout, setup-python, setup-uv, upload/download-artifact)"*. | `ci.yml` pins no `download-artifact`. Its newest release, v8.0.2, is 2026-10-07 — 13 days old, under the 14-day rule. | **`actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` (v8.0.1, 2026-03-11)**; the others copied from `ci.yml` (checkout v7.0.1, setup-python v7.0.0, setup-uv v9.0.0 with uv 0.12.1, upload-artifact v7.0.1); `pypa/gh-action-pypi-publish@dc37677b…` (v1.14.2, rig 43d). | Every action a commit, every commit old enough to have been looked at. | 0284 |
| **D2707** | D2667: *"`verify` … passes only if a `contract` run for that SHA concluded `success` — empty list or any other conclusion fails"*. | A commit can carry more than one `contract` run (a re-run). `ci.yml` cancels in-progress runs on `main`, so a deploy commit followed quickly by another push has a CANCELLED run. | **The LATEST `contract` run (by `run_number`) must have concluded `success`**; none registered fails (D1057), and so does a later failure after an earlier success. The step is EXECUTED in `test_publish_verifies_the_contract_run` against a fake `gh` (the real `jq`), seven cases. The deploy commit's own `contract` run must be green before the tag — a cancelled one means re-running it first. | The release tag publishes only what its commit's current verdict allows. | 0284 |
| **D2708** | D2662: the build refuses *"a `FORBIDDEN_WORDS` member"* in any page. | The Ledger page (D2674) prints every row's CONCEPT, and a `not_offered` row is named `Autoscaling` precisely to say it is not offered; `reality_ledger.forbidden_words_in` reads `customer_text`, not concept names. | **The site's word scan reads every page's prose and the Ledger page's two customer-facing columns** (*Today*, *What you get*), not its concept names; `test_no_forbidden_word` says so and counts the cells it read. | Naming a concept to say it is absent is the opposite of the claim §59 forbids. | 0283 |
| **D2709** | D2662's page list; ADR 0283's digest inputs (*`site/**`, `plans.py`, `reality-ledger.yaml`, `VERSION`*). | `docs/managed-projects.md`'s life-of-a-project sections (states, creation and the claim, sleeping, sizes, export, deletion) had no page in D2662's list; a pointer alone would have lost them. The renderer's own grammar decides the bytes too. | **`site/pages/docs/projects.md` added** (13 pages + `404.html`); the **digest also covers `src/agentic_postgres/site_build.py`**; generated bodies are a page whose whole body is `@pricing` or `@ledger` (any other `@` line is refused); the Ledger page's front matter is `ledger: "*"` and only it may be. `docs/managed-projects.md` is the pointer; `control-plane.md`'s command list and *"no web console … no `apg project status`"* rewritten (both exist now); `monitoring.md`'s customer half moved to the site page, its reference kept. | One source for what a stranger reads, and nothing the old page said lost on the way. | 0283 |
| **D2710** | Run 7 step 7's battery: *"write `$5/month` into `pricing.md`"*, *"add `<img …>` via a raw HTML line"*. | The BUILD refuses both before any test reads a page, so those tests would ERROR, not fail (D386). | **The two mutations remove the guard instead** (the build's price check; the renderer's raw-HTML check), killed by each test's own control; the plan's other two as written, and an *any https origin* mutation added — 5/5. | A mutation is evidence only when it fails the assertion it names. | — |
| **D2711** | Run 7 step 8: *"if the project does not exist, wrangler creates it — rig 43c recorded whether it does; if it does not, the agent creates it through the API"*. | Rig 43c: `wrangler pages deploy` to an absent project answers *"The Pages project … does not exist"*. | **The agent created `agentic-postgres-site` through the API** (production branch `main`, `agentic-postgres-site.pages.dev`, no deployment) before the push that adds `site.yml`. | The first workflow run must have somewhere to upload. | 0283 |
| **D2712** | D2665: *"Run 9: `management_api.customer_text` … rewritten to what the tree does"*. | The site prints every row's `customer_text` and goes live with this run's push; `management_api` still said *"Creating a project is not available yet and says so"*, false since Session 38. | **Rewritten in Run 7**: *"… manages accounts, organizations, members, invitations and keys, and creates and manages your projects, their branches, their connections and their backups."* `cli_remote`'s stays for Run 9: the package it would name is not published until the tag. | A sentence is corrected before it becomes public, not after. | 0254 |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**Two new families, `CON` and `SITE`** (the stage plan proposes `CON-*`; the
site is a separate surface with its own build and guards): the regex at
`tests/contract/test_acceptance_registry.py:127` gains `CON|SITE`, and the
family comments (`:50-126`) gain one sentence after Session 42's (`:124-126`):
*Session 43 (ADR 0280-0284) adds `CON` for the console, its session and
onboarding, and `SITE` for the public site.* **`CON-` does not collide with
`CONN-`**: the alternation is followed by `-` (measured by the explore pass;
Run 9 adds `test_con_and_conn_are_distinct_prefixes` to be sure). The packaged
CLI goes under `DX` (the stage plan's *"`DX-*` extended"*) and the three repairs
under the families their existing proofs live in — **Run 9 greps the registry
for the family of each repaired command's existing proof and its next free
number** (`grep -n "telemetry.sh\|provision-host\|bootstrap-providers"
tests/acceptance-registry.yaml`); the ids below are proposed. **Twenty
requirements, twenty claims, all `target_session: 43`, all P0 — sixteen
offline, one host, three external.** Node ids are **proposed; Run 9 writes what
the runs actually wrote**, read with `pytest --collect-only -q` (D1236, D2129).
Committed by Run 9 with the constant (D690), under **`# Session 43 (ADR
0280-0284)`**.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `INS-STATUS-001` | `telemetry.sh status` reads every container of the plane, one with no healthcheck included, and names the one it could not read | `tests/contract/test_telemetry_status.py::test_a_container_without_a_healthcheck_is_read`, `::test_a_container_with_one_is_read` | — (`telemetry_status_reads_all`) |
| `DEP-LAUNCH-001` (family read by Run 9) | `provision-host.sh --check` verifies exactly the launchers the install installs | `tests/contract/test_provision_host_launchers.py::test_the_check_reads_the_install_glob`, `::test_a_seventh_launcher_is_checked` | — (`launcher_check_reads_the_install`) |
| `OPS-PROV-002` (family read by Run 9) | `bootstrap-providers --apply` prints the number of resources it created | `tests/contract/test_bootstrap_providers.py::test_the_created_count_is_read` | — (`provider_count_is_read`) |
| `CON-SESSION-001` | With `X-Apg-Console: 1` the session routes set the two `__Host-` cookies `HttpOnly; Secure; SameSite=Strict; Path=/` and answer no token; refresh and logout read the cookie; logout clears both; a bearer request is unchanged and ignores cookies; a key never rides a cookie | `tests/contract/test_console_session.py::test_the_console_login_sets_two_host_cookies`, `::test_the_console_login_body_holds_no_token`, `::test_refresh_reads_the_cookie`, `::test_logout_clears_both`, `::test_a_bearer_request_ignores_cookies`, `::test_a_key_in_a_cookie_is_refused` | — (`console_session_cookie`) |
| `CON-CSRF-001` | A cookie is honoured only with `X-Apg-Console: 1`; a write needs `Origin` equal to the console's origin; no CORS header is ever answered; no log line holds a cookie value | `tests/contract/test_console_session.py::test_a_cookie_without_the_header_is_unauthenticated`, `::test_a_write_from_another_origin_is_refused`, `::test_a_write_without_an_origin_is_refused`, `::test_no_cors_header_is_answered`, `::test_no_line_holds_a_cookie_value` | — (`console_csrf_rule`) |
| `CON-INVITE-001` | The mint answers `accept_url` = the console origin + `/accept#` + the token; `org invite` writes the link; `login accept` reads a token or a link and refuses anything else; no log line holds the token | `tests/contract/test_console_session.py::test_the_mint_answers_the_accept_url`, `::test_no_line_holds_the_invitation_token`, `tests/contract/test_control_cli.py::test_invite_writes_the_link`, `::test_accept_reads_a_token_or_a_link` | — (`invitation_link`) |
| `CON-FACTOR-001` | The enrolment answer carries `otpauth_qr`, an SVG data URI of `otpauth_uri` with no external reference; segno is pinned and imported by the image's build control | `tests/contract/test_console_session.py::test_the_enrolment_answer_carries_the_qr`, `::test_the_qr_references_nothing`, `tests/contract/test_version_lock.py::test_segno_is_locked` | — (`factor_qr`) |
| `CON-SERVE-001` | The console server: a fixed route table, GET and HEAD only, the exact CSP and security headers on every answer (404 and redirect included), no query and no header logged, no `<script src>` or `<link href>` that is not a relative path of its own | `tests/contract/test_console_server.py::test_only_the_listed_paths_answer`, `::test_every_answer_carries_the_policy`, `::test_the_log_names_no_query`, `::test_every_asset_is_our_own_file`, `::test_no_method_but_get_and_head` | — (`console_server`) |
| `CON-PLANE-001` | The `console` service: bounded, read-only, no secret, no mount, network `edge` only, profile `console` added only for the control project, its router rule exactly `/`, `/accept`, `/console/…` on the project's host | `tests/contract/test_process_limits.py::test_the_console_is_bounded`, `tests/contract/test_console_plane.py::test_the_profile_is_added_only_for_the_control_project`, `::test_the_router_rule_is_the_three_paths`, `::test_the_console_holds_no_secret_and_no_mount` | — (`console_plane`) |
| `CON-LEDGER-001` | Every console page names a Ledger row that is reachable, every `/v1` path its scripts call exists in the control snapshot, no page names a `planned` or `not_offered` row, no script builds SQL | `tests/contract/test_reality_ledger.py::test_every_console_page_maps_to_a_reachable_row` (replaces `test_no_console_exists_yet`), `tests/contract/test_console_pages.py::test_every_called_path_is_in_the_snapshot`, `::test_no_page_names_an_unreachable_row`, `::test_no_script_holds_sql` | — (`console_ledger_map`) |
| `CON-SCRAM-001` | The console's verifier equals `scram.verifier` for the same password and salt; the password is never written to storage or a URL | `tests/contract/test_console_scram.py::test_the_browser_verifier_equals_the_clis`, `tests/contract/test_console_pages.py::test_no_script_writes_storage` | — (`console_scram`) |
| `SITE-BUILD-001` | The site builds from the tree alone, twice byte-equal; the pricing page is the entitlements of `PLANS` and the beta sentence, with no price; the Ledger page is the YAML's rows; the subset renderer refuses raw HTML | `tests/contract/test_site.py::test_two_builds_are_byte_equal`, `::test_the_pricing_page_follows_the_plans`, `::test_no_price_is_printed`, `::test_the_ledger_page_is_the_rows`, `::test_raw_html_is_refused`, `::test_the_site_names_no_host_address` | — (`site_build`) |
| `SITE-CLAIM-001` | Every page names its Ledger rows and each is reachable; no page holds a forbidden word, `bin/`, `sudo`, `ssh `, `git clone` or `--session`; no asset is third-party; `_headers` carries the site's CSP | `tests/contract/test_site.py::test_every_page_names_reachable_rows`, `::test_no_page_holds_an_operator_command`, `::test_no_forbidden_word`, `::test_no_third_party_asset`, `::test_the_headers_file_carries_the_policy` | — (`site_claims`) |
| `SITE-DEPLOY-001` | The site workflow deploys only after `contract` succeeded on `main`, checks out that run's SHA, pins wrangler and every action, holds the token only in the `site` environment | `tests/contract/test_release_workflows.py::test_the_site_deploys_only_after_contract`, `::test_the_site_workflow_pins_everything` | — (`site_workflow`) |
| `DX-PKG-001` | The staged CLI differs from its sources only inside the seam; it imports only the standard library and itself; the wheel installs offline into a clean Python and runs `apg --version` and every family's `--help`; its version is `VERSION` | `tests/contract/test_cli_package.py::test_the_stage_differs_only_in_the_seam`, `::test_the_package_imports_only_stdlib`, `::test_the_wheel_runs_every_family`, `::test_the_version_is_the_release` | — (`cli_package`) |
| `DX-PKG-002` | The publish workflow runs only on a release tag, verifies that SHA's `contract` success (an empty list fails), grants `id-token: write` to the publish job alone, pins the publish action by SHA | `tests/contract/test_release_workflows.py::test_publish_runs_only_on_a_release_tag`, `::test_publish_verifies_the_contract_run`, `::test_only_the_publish_job_has_id_token`, `::test_publish_pins_the_action` | — (`cli_publish_workflow`) |
| `CON-HOST-001` | On the host: the console runs on `control-prod` only, bounded, healthy; no other project runs it; the listeners did not change | — | `tests/deployment/test_session43_console_host.py::test_the_console_runs_only_on_the_control_project`, `::test_the_console_is_bounded`, `::test_the_listeners_did_not_change` (host `console_live_host`) |
| `CON-LIVE-001` | Through the public origin with no SSH: an invitation link opened in a browser reaches an account, a confirmed factor, a session cookie, the Connect page, a password shown once (and gone on reload), and that password connects over TLS; the first paint and the link-to-string time recorded | — | `tests/external/test_session43_console.py::test_the_walk_reached_every_step`, `::test_the_password_was_shown_once`, `::test_the_string_from_the_page_connects`, `::test_the_times_were_recorded`, `::test_this_module_uses_no_ssh` (external `console_walk_live`) |
| `CON-LIVE-002` | Live: the console's answers carry the exact policy; a cookie without the header, and a write from another origin, are refused; the accept page's request line never held the token; the session cookies are `HttpOnly`/`Secure`/`Strict` | — | `tests/external/test_session43_console.py::test_the_public_answers_carry_the_policy`, `::test_a_cookie_alone_is_refused_live`, `::test_a_foreign_origin_write_is_refused_live`, `::test_the_cookies_were_strict` (external `console_csrf_live`) |
| `SITE-LIVE-001` | The apex and `www` serve the site built from the evidence commit's inputs (the build digest matches), with the CSP header, no request to any other host, and the pricing page's plans equal to `GET /v1/plans` | — | `tests/external/test_session43_console.py::test_the_site_is_the_commits_build`, `::test_the_site_loads_nothing_else`, `::test_the_pricing_page_matches_the_api` (external `site_live`) |

**Expected counts** — Run 9 counts them from the tuples, never from this prose
(D1628): requirements **395 → 415**, `CLAIMS` **302 → 322**, `OFFLINE_CLAIMS`
**133 → 149**, ADRs **279 → 284**.

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, a block
commented *Session 43 (ADR 0280-0284)* after Session 42's `:946-969`): offline —
`telemetry_status_reads_all`, `launcher_check_reads_the_install`,
`provider_count_is_read`, `console_session_cookie`, `console_csrf_rule`,
`invitation_link`, `factor_qr`, `console_server`, `console_plane`,
`console_ledger_map`, `console_scram`, `site_build`, `site_claims`,
`site_workflow`, `cli_package`, `cli_publish_workflow` — **these sixteen** go
in `OFFLINE_CLAIMS` with the per-session assertion in
`test_session_forty_three_gate_modes.py` (D1237: assert THESE are in the set,
never its size). Host — `console_live_host`. External — `console_walk_live`,
`console_csrf_live`, `site_live`. `CLAIM_INTRODUCED_IN`
(`tests/contract/test_evidence_claims.py:953-1345`) gains a row at 43 for each.

**Existing entries that move** (each a passing proof made stricter or replaced
by a stricter one under the ADR named — CLAUDE.md §6):

- **`LEDGER-001`**: `test_no_console_exists_yet` is **replaced** by
  `test_every_console_page_maps_to_a_reachable_row` (ADR 0280; the old test's
  own docstring names this replacement, `test_reality_ledger.py:252-258`).
- **The `plan notify-me` proof** in `tests/contract/test_control_cli.py` that
  reads `INTEREST_PLANS` (Run 6 greps `grep -n "INTEREST_PLANS\|notify-me"
  tests/contract`) is re-pointed to the `/v1/plans` reading (D1119 if renamed).
- **`test_documentation_index.py`/`test_session12_documented_path.py`**:
  unchanged; `docs/managed-projects.md` stays a linked page (now a pointer).
- **`THR-*` rows**: five added in Run 1 (§5); none removed.

**New environment gates: one** — `APG_CONSOLE_RECORD_FILE` (D2668), in the
roster `tests/conftest.py:86-225` after Session 40's `:224`, exported by the
gate's external mode (D2677). **Read in a test body with `.get(...)`, never
`x["APG_…"]`** (D2381).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| **The foreign Worker route and the wildcard AAAA deleted from the zone** | Sheet C0 (Run 1, the agent) | The operator's decision of 2026-10-19 (D2650); both re-read by id and compared to p5/p6 first; the Worker SCRIPT untouched; a route someone recreates is a row, not a retry |
| **Email Routing enabled; MX and TXT records added** | Sheet C1 (Run 1, the operator) | Forward-only; DNS-only by construction; read back by the agent; no other record touched |
| **A PyPI pending publisher for `agentic-postgres-cli`** | Sheet C2 (Run 1, the operator) | Names one workflow and one environment; reserves nothing (Run 1 reads it); removable in pypi.org |
| **A Cloudflare API token (Pages:Edit, this account) and the GitHub environments `site` and `pypi`** | Sheet C3 (Run 1, the operator) | The token never enters the conversation or the tree (the operator pastes it into GitHub's secret form); `pypi` holds no secret at all (trusted publishing) |
| **The Pages project `agentic-postgres-site` and its two custom domains** | Sheet C4 (Run 7) | Created by the first workflow run, the domains attached by the agent through the API and read back proxied; every host A record read still DNS-only |
| **The site public at the apex and `www`** | Run 7 onward, every green push to `main` | Built only after `contract` succeeds; the Ledger guard and the word scan are in the build itself |
| `CURRENT_SESSION` 42 → 43; `VERSION` 1.20.0 → 1.21.0; `console` → `trial`; `sql_editor` → `planned` (44); the schema's maximum → 45 | Run 9 | All-or-nothing (D690); `README.md:7` and every `--session 42`/`--through-session 42` literal on the documented path moved and counted per file (D678/D1484); ADRs 0261, 0280 |
| `bin/session-43-check.sh` | Run 9 | Derived from 42's by diff (D1482); header and usage rewritten whole (D1488); one flag added (D2677); `SHELL_COMMANDS`; `chmod 755` before `git add` |
| **1.21.0 deployed on the four projects; the console started on `control-prod`** | Sheets R2a–R2d (Run 10) | The reconciler stopped (D2178); one project at a time, each window probed; control-prod last; no database restart (no command change) |
| **`slot3-prod`'s `customer_app` password rotated by the browser walk** | Run 10 (W1) | The probe organisation's own project and the customer's own act through `/v1`; the old creds file copied `.before-s43`, the new one written 0600 by the instrument; `customer_admin` untouched |
| **A walker account and its membership in `probe-s37`** | Run 10 (W0, W1) | Membership removed after; accounts are never deleted (D2065) — §10 |
| Tag `1.21.0` on the deployed commit | Run 10 | After the merge exits 5 for `documented_path` only (§7); from the WORKSTATION (D2041) |
| **`agentic-postgres-cli 1.21.0` published to PyPI** | Run 10, by the tag | Only after `verify` reads that SHA's `contract` success; a PyPI version can be yanked and never re-uploaded under the same number — a defect found after is the next release's |

---

## 5. Build order, run by run

Each run ends with a `**Done.**` paragraph written by the executor: what was
measured, the numbers, the rows it added, and — for a code run — the CI verdict
by full SHA (and, from Run 7, the `site` workflow's). The targeted modules run
ONCE at the run's close and only a failing module is re-run. `ruff format &&
ruff check` before every commit; `chmod 755 bin/*.sh bin/*.py deploy.sh
libexec/*` before every `git add` — **and every file an image executes
directly** (D2412); messages from a file with `-F`, ending with the attribution
line the session's system reminder gives. **Grep the plans for every third
party before measuring it.** **A run that renames, adds or removes a test
function runs `test_acceptance_registry` and `test_evidence_claims`** (D1119);
**a run that adds a module under `src/agentic_postgres/` runs
`test_repository_contract`** (D2114; the module needs a `bin/` caller,
`:616-650`); **a run that adds or removes a `bin/` command runs
`test_cli_contract` and `git add`s it first** (D1014); **a run that adds a
`document[...]` read to a `bin/` command runs `test_container_selectors`**
(D1184); **a run that touches a documentation page runs
`test_documentation_index` and `test_session12_documented_path`**; **a run that
touches `.github/workflows/` runs `test_gate_contract`** (it reads every
workflow, `:208-235`); **every new test module carries `pytestmark` before its
first test** (D1240), and the sweep-selector guard (D1242) AND
`test_environment_gates` join the targeted list of any run that adds a module —
**read a model dict with `.get("APG_…")`, never `x["APG_…"]`** (D2381).
**Docker-backed modules reuse `tests/contract/control_cluster.py`** (`docker rm
-fv`, D2098). **Every external fixture that holds a password, verifier, token or
TOTP seed returns `tests/external/redaction.py`'s `Secret`** (D2420). **Never
print a live log's failure body without filtering it by the secret VALUES**
(D2416). **Every mutation battery** follows CLAUDE.md §1:
`PYTHONDONTWRITEBYTECODE=1`, snapshot to `/tmp` and restore by copy with `cmp`,
anchors pre-flighted (a miss fatal), a control the mutation cannot reach, and
*how* each failed (`FAILED` vs `ERROR`). **Never put `--` inside a SQL string
literal in a migration template, and never backticks in an inline heredoc.**
**No build output inside the tree**: `bin/build-site.py` and `bin/build-cli.py`
refuse an `--out` under the repository (the gate's step 1 fails on any
untracked file, `bin/session-01-check.sh:85-90`); tests build into `tmp_path`.

### Run 1 — the zone, the consoles, the rigs, the threat items, ADRs 0280–0284

**Documentation, one agent act on the zone, three operator sheets; no code; no
CI read.**

**Read first:** this plan §0 and §1 whole; `docs/plans/session-42-implementation-plan.md:476-481`
(D2591–D2596); ADRs 0069, 0205, 0246, 0252, 0268; `services/docs/serve.py`
whole; `docs/threat-model.md:184-201` (the hosted list's preamble) and `:358-381`
(items 14–15, the shape to copy); `docs/decisions/README.md:300-345`.

**Step 1 — Sheet C0 (the agent; D2650).** Through the Cloudflare API (the
`cloudflare-api` MCP tool, or `curl` with a token the operator hands for the
step): resolve the zone id by name; `GET /zones/{zone}/workers/routes` and
`GET /zones/{zone}/dns_records?type=AAAA&name=*.agenticpostgresql.com`; **stop
(§9) unless** exactly one route `*.agenticpostgresql.com/*` → `forgeai-sandbox`
and exactly one proxied AAAA `*` → `100::` are found; `DELETE` the route by id,
`DELETE` the record by id; read both lists again (absent). Read
`nslookup www.agenticpostgresql.com 1.1.1.1` (no answer expected) and every
A record unchanged (24 − 1 = 23 records, all `proxied: false`). The Worker
script is read present and left alone. Recorded in the `**Done.**` with the ids.

**Step 2 — Sheets C1, C2, C3 handed to the operator** (appendix); each is read
back by the agent before Run 7 depends on it. C1 (Email Routing) is read by the
MX/TXT records through the API and the operator's test mail; C2 (the pending
publisher) by the operator's screenshot-free description of the form's five
values, recorded verbatim; C3 by `gh api repos/Virabyan99/agentic-postgres/environments
-R …` from Git Bash listing `site` and `pypi` (names only; the secret is never
read back).

**Step 3 — the rigs**, each in its own throwaway directory under `~/s43/rigs/`
on WSL, each with its control, each result written to `~/s43/rigs/<rig>.txt` as
it is taken:

- **Rig 43a — cookies, origins and WebCrypto in a real browser.** In the pinned
  Playwright image (rig 43e first): a 40-line stdlib `http.server` on
  `127.0.0.1:18443` with a self-signed certificate (`openssl req -x509` in the
  rig, `ignore_https_errors=True` in the context) serving `/login` (sets
  `__Host-a=1; HttpOnly; Secure; SameSite=Strict; Path=/`), `/echo` (answers the
  `Cookie`, `Origin` and `X-Apg-Console` it received) and a page that `fetch`es
  `/echo` with the header; a second origin `https://localhost:18444` serving a
  page that (i) `fetch`es `https://127.0.0.1:18443/echo` with the header, (ii)
  submits a `<form method=post>` to it, (iii) navigates to it. **Measure**: (1)
  the same-origin `fetch` carries the cookie and the header; (2) the cross-origin
  `fetch` with the custom header is **never sent** (a preflight `OPTIONS` arrives
  and nothing answers it — the `/echo` log shows only the `OPTIONS`); (3) the
  cross-site form POST arrives **without the cookie**; (4) the top-level
  navigation from the other site arrives **without the cookie** (Strict) — the
  **control**: the same three with `SameSite=Lax` show (4) carrying it; (5)
  `document.cookie` on the first origin reads `""` (HttpOnly); (6) Chromium's
  `crypto.subtle` PBKDF2 4,096 × SHA-256 of a fixed password and salt equals
  `hashlib.pbkdf2_hmac` (the **control**: 4,095 iterations differ). **If (2)
  arrives at the handler, or (3)/(4) carry the cookie, §9's stop.**
- **Rig 43b — the QR.** `segno`: the newest release on PyPI at least 14 days
  old (`https://pypi.org/pypi/segno/json`), its licence, its `requires_dist`
  (expected: none), the sha256 of its wheel. In a throwaway `python:3.12`
  container (the digest `versions.env` pins as `PYTHON_BASE_IMAGE`): `pip
  install segno==<v>`; `segno.make(uri, error="m").svg_data_uri(scale=4)` for a
  fixture URI `otpauth://totp/agentic-postgres:rig?secret=JBSWY3DPEHPK3PXP&issuer=agentic-postgres&period=30&digits=6&algorithm=SHA1`;
  decode the SVG (rasterised by `rsvg-convert` from `librsvg2-bin`) with
  `zbarimg` (`zbar-tools`) in a throwaway `debian:stable-slim` → **exactly the
  URI**; **control**: a second URI differing in one character decodes to itself,
  not the first. Read that the data URI contains no `http` and no `<script`.
- **Rig 43c — Cloudflare Pages** (D2676). The operator creates a **temporary**
  token (Pages:Edit) for the rig and pastes it into a 0600 file in WSL by
  `nano` (never into the conversation); the agent creates `apg-rig-43c`, uploads
  `index.html`, `a/index.html`, `404.html` and `_headers` (`/*` →
  `Content-Security-Policy: default-src 'none'; style-src 'self'`, and `/a/*` →
  `X-Rig: a`) with **wrangler** in the pinned Node image (`NODE_BASE_IMAGE`,
  `npx --yes wrangler@<x.y.z>`; the version read as the newest ≥ 14 days old and
  recorded); reads `curl -sI https://apg-rig-43c.pages.dev/`, `/a/`, `/missing`
  — the CSP on all three; `X-Rig` only on `/a/` (**the control**); `/missing` →
  404 with `404.html`'s body; and whether Pages adds headers of its own
  (recorded whole). Then deletes the project, reads it gone, **and the operator
  revokes the token** (read: a call with it answers 401).
- **Rig 43d — the wheel and the publish action.** In a throwaway copy of the
  tree: stage `apg_cli` by hand the way D2666 describes (the seam replaced), add
  the generated `pyproject.toml`, `uv build` (the uv the workstation has, the
  version recorded), install the wheel into a clean `python:3.12` container with
  `--network none` (`pip install --no-index /dist/*.whl`), run `apg --help` and
  `apg login --help` — **control**: `bin/cloud.py --help` from the tree prints
  the same usage text. Then the same in `python:3.10-slim` and `3.11-slim` (by
  digest, read on Docker Hub): the lowest that passes decides
  `requires-python` (D2666). Read `pypa/gh-action-pypi-publish`'s newest release
  ≥ 14 days old and **its commit SHA** (`gh api
  repos/pypa/gh-action-pypi-publish/git/ref/tags/<tag>`, dereferenced to the
  commit). **Read PyPI's documentation on pending publishers** and record the
  sentence about reserving a name verbatim with its URL (D2652).
- **Rig 43e — Playwright.** `mcr.microsoft.com/playwright/python`: the newest
  tag ≥ 14 days old and its digest (`docker buildx imagetools inspect`); inside:
  `python -c "import playwright, sys; print(playwright.__version__)"`, Chromium
  launches headless, a page's `performance.getEntriesByType('paint')` holds
  `first-contentful-paint` (**control**: an `about:blank` page holds none). The
  image size recorded (it is pulled once per sitting).

**Step 4 — the threat items.** `docs/threat-model.md`'s hosted list gains
**items 16–20** after item 15 (`:373-381`), each with its threat, the control
this session builds and the test that holds it: **16 Console session theft**
(XSS → the CSP `default-src 'none'; script-src 'self'`, no inline script, no
third-party file; HttpOnly), **17 Cross-site requests with the console's
session** (Strict + the header + `Origin`; no CORS), **18 An invitation link
leaks** (fragment; `replaceState`; `no-referrer`; 72 h default; single use),
**19 The public site claims more than the node does** (the build's Ledger guard
and word scan; the pricing from `PLANS`), **20 A supply-chain path into what a
customer runs** (the console: own files only; the site: CI-built after the full
check; the CLI: tag + `contract` success + trusted publishing, actions pinned
by SHA, no stored token). The `THR-*` table (`:17-68`) gains **five rows**
after `THR-INS-UI` (`:68`), `Target session` 43: `THR-CON-XSS`, `THR-CON-CSRF`,
`THR-CON-LINK`, `THR-SITE-CLAIM`, `THR-SUPPLY` — and **one carried row**
`THR-CON-GUESS` (D2679: password and TOTP guessing at an unthrottled door, the
edge's 20/s the only limit; named, not changed).

**Step 5 — ADRs 0280–0284** (`docs/decisions/0280-…md` … `0284-…md`), indexed
in `docs/decisions/README.md` after `:345`, each with Context, Decision,
Alternatives, Consequences in the shape of 0277–0279:

- **0280 — The console is a first-party fixed-route static server on the
  control project's origin.** D2655, D2661, D2668's measurement; the route rule;
  the facility profile; every page mapped to a Ledger row; no data view; the CSP
  (exact string, below); `test_no_console_exists_yet` replaced.
- **0281 — The console's session is a pair of `__Host-` cookies, chosen per
  request by a header, and a write needs the console's `Origin`.** D2656, D2678;
  rig 43a's six readings; bearer precedence; keys never.
- **0282 — The invitation is a link with the token in its fragment, and the
  factor's QR is drawn by the server.** D2657, D2659, D2658's sentence; rig 43b.
- **0283 — The public site: static files built from the repository, published
  to Cloudflare Pages by CI, every claim from the Ledger, nothing third-party.**
  D2650, D2651, D2653, D2654, D2662–D2664, D2674, D2676; rig 43c; **the
  grey-cloud rule's scope sentence** (D2651); no tracker (D2596): traffic read
  from Pages' own numbers; Web Analytics only by a later operator decision.
- **0284 — The customer CLI is staged from the repository's own files and
  published to PyPI by trusted publishing from a release tag.** D2652, D2666,
  D2667; rig 43d's readings (`requires-python`, the action's SHA, PyPI's
  sentence on pending publishers).

**The console's Content-Security-Policy** (ADR 0280 states it; Run 4 implements
it as one constant; no `'unsafe-inline'` anywhere, because the console's CSS is
our own file):

```
default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:;
connect-src 'self'; font-src 'none'; base-uri 'none'; form-action 'none';
frame-ancestors 'none'
```

**The site's** (ADR 0283; `_headers`, `/*`): the same with `connect-src 'none'`
and `img-src 'self'` (the site fetches nothing and draws no data URI).

**Done.** 2026-10-19 (rigs in WSL `~/s43/rigs/`, each `<rig>.txt` written as
taken; the scripts copied beside them). Rows **D2680–D2687**.

- **Sheet C0** (the agent, Cloudflare API): zone
  `5f7560988cc4d6d45c29425f6365ef0e`; exactly one route
  `d1d4ee079f7343fe8c0ab6abf691ef9e` (`*.agenticpostgresql.com/*` →
  `forgeai-sandbox`) and exactly one AAAA `eff5ae89635ee0bd496cda5085030871`
  (`*` → `100::`, proxied), as p5/p6. Both DELETEd (200, 200); read again:
  no route, no AAAA, **28 records** (the plan's 23 A + C1's 3 MX and 2 TXT),
  every one `proxied: false`. `forgeai-sandbox` read present, untouched.
  `nslookup www.agenticpostgresql.com 1.1.1.1` → *Non-existent domain*; `curl`
  → exit 6.
- **C1–C3** were done by the operator before the run (CLAUDE.md's record) and
  read back: C1's records in the zone listing above; C3 by `gh api
  …/environments` → `pypi` and `site`, each `custom_branch_policies: true`; C2
  as recorded. `agentic-postgres-cli` and `agentic-postgres` still **404** on
  PyPI at 19:4xZ.
- **Licence (§9's Run 6 stop, raised early)**: none in the tree, the
  repository public. **The operator: Apache-2.0** (D2685; the file lands in
  Run 6).
- **Rig 43a** (Chromium 153.0.8010.12): all six readings as planned —
  same-origin POST carries both cookies, the header and `Origin`; the
  cross-origin `fetch` with the header reaches the server only as `OPTIONS`
  with no cookie; the cross-site form POST carries no cookie; a cross-site
  navigation carries the Lax control and not the Strict cookie;
  `document.cookie` = `""`; WebCrypto PBKDF2 4,096 = `hashlib`
  (`4b041b5f…`), 4,095 differs.
- **Rig 43b**: `segno` 1.6.6 (BSD, no dependency on 3.12, wheel sha256
  `28c7d081…190c7`); decodes exactly only on a white background —
  **`light="white"`** (D2682); `http` only as the SVG namespace.
- **Rig 43c** (wrangler **4.147.0**): `_headers` applies everywhere, `404.html`
  served with 404, `Referrer-Policy` overrides, `!` detaches ACAO, X-Rig only on
  `/a/` (control); Cloudflare's NEL cannot be detached — not a stop, the
  agent's ruling (D2687). The project deleted and read gone; **the operator
  revoked the temporary token**: `/user/tokens/verify` with it → **401**
  (`1000 Invalid API Token`), then the file shredded.
- **Rig 43d** (uv 0.12.1): the staged wheel runs byte-equal to the tree's usage
  on 3.12 and 3.11; **3.10 fails** (`datetime.UTC`) → `>=3.11` (D2683);
  `prog="cloud.py"` and `--help` exiting 2 (D2684). `pypa/gh-action-pypi-publish`
  **v1.14.2** → commit **`dc37677b2e1c63e2034f94d8a5b11f265b73ba33`**. PyPI's
  sentence (<https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/>):
  *"A "pending" publisher does not create a project or reserve a project's name
  until it is actually used to publish. If you create a "pending" publisher but
  another user registers the project name before you actually publish to it,
  your "pending" publisher will be invalidated."*
- **Rig 43e**: `mcr.microsoft.com/playwright/python:v1.63.0-noble@sha256:72bd171a9ffc2b4b59532aaa6210e21014d07093120dc25528870c0b840da1f0`
  (1,013,940,272 bytes; Playwright 1.63.0, 2026-09-15) — the package is **not**
  in it (D2686); installed with `--target`, FCP read (124 ms), `about:blank`
  none.
- **Step 4**: `docs/threat-model.md` hosted items **16–21**; the table rows
  move in Run 9 (D2681).
- **Step 5**: `docs/decisions/0280-the-console-is-a-first-party-fixed-route-static-server-on-the-control-projects-origin.md`,
  `0281-the-consoles-session-is-a-pair-of-host-cookies-chosen-per-request-by-a-header-and-a-write-needs-the-consoles-origin.md`,
  `0282-the-invitation-is-a-link-with-the-token-in-its-fragment-and-the-factors-qr-is-drawn-by-the-server.md`,
  `0283-the-public-site-is-static-files-built-from-the-repository-published-to-cloudflare-pages-by-ci-every-claim-from-the-ledger.md`,
  `0284-the-customer-cli-is-staged-from-the-repositorys-own-files-and-published-to-pypi-by-trusted-publishing-from-a-release-tag.md`,
  indexed. Documentation only: pushed, no CI read.

### Run 2 — the three repairs: D2636, D2637, D2642 (`bin/`, tests)

**Read first:** D2670; `bin/telemetry.sh:150-200`; `bin/provision-host.sh`
(`install_launchers` — `grep -n "install_launchers\|libexec/agentic-postgres-"
bin/provision-host.sh`) and `:320-345`; `bin/bootstrap-providers.py:960-1035`;
`tests/contract/test_diagnostic_surface.py:475-526` (the fake-docker pattern);
the existing tests of each command (`grep -ln "telemetry.sh\|provision-host\|bootstrap-providers"
tests/contract/*.py`).

1. **D2636 — failing test first.** Reproduce with the pinned collector image
   (`versions.env` `OTEL_COLLECTOR_IMAGE`): `docker run -d --name s43-nohc
   <image>`; the current template from `:172` → rc 1; each candidate from D2670
   → record which prints `health=none` with rc 0; `docker rm -fv s43-nohc`.
   Write `tests/contract/test_telemetry_status.py` (Docker-backed, `pytestmark`
   first): start one container with no healthcheck and one with
   (`--health-cmd true`), run `do_status`'s template through the script (source
   `bin/telemetry.sh` with `main` removed, the `test_diagnostic_surface.py`
   pattern, `require_root` stubbed and `compose` replaced by a function printing
   the two ids) → both lines read, `health=none` for the first; **red before the
   fix**. Fix the template; green.
2. **D2637 — failing test first.** `tests/contract/test_provision_host_launchers.py`:
   a temporary `LIBEXEC` and a temporary repository `libexec/` holding the six
   launchers plus `agentic-postgres-seventh`; run `--check`'s launcher block
   (source with `main` removed; read the variables it needs) → it must name
   `seventh` as missing from `LIBEXEC` before the install and `ok` after; **red
   before the fix** (the typed list never names it). Fix: one function
   `launcher_names` reads `"${REPO_ROOT}/libexec"/agentic-postgres-*` (the glob
   the install reads — read the install's exact glob and reuse that expression),
   strips the prefix, and both the install and the check call it.
3. **D2642 — failing test first.** Read what `--apply` holds when it reaches
   `:1027` (the created resources' list or dict — `sed -n 960,1030p
   bin/bootstrap-providers.py`); the test drives `--apply` through its existing
   test harness (`grep -n "def test.*apply" tests/contract/test_bootstrap_providers*.py`)
   with a plan of a known count and asserts the printed number equals it;
   **red before** (it prints 4). Fix: `len(<that list>)`.
4. **Battery** (CLAUDE.md §1): for each fix, revert it alone → its own test
   FAILED (not ERROR), the other two green (the control).
5. Targeted: the three new modules, `test_cli_contract`,
   `test_diagnostic_surface`, `test_repository_contract`, `test_environment_gates`,
   the sweep-selector guard. Commit `fix(session-43): Run 2 -- telemetry status,
   the launcher check, the provider count (D2636, D2637, D2642)`; push; read CI.

**Done.** 2026-10-20 (WSL `~/s43/run2/`). Rows **D2688, D2689**.

- **D2636**: `{{if index .State "Health"}}` — the first candidate printing
  `health=none` rc 0 in the FULL template; the cause is the CLI's typed→map
  fallback forced by `NanoCpus` (D2688). `tests/contract/test_telemetry_status.py`
  (Docker-backed, the pinned collector image, `do_status` from a copy with only
  `ROOT_DIR`, `main`, `require_root` and `compose` replaced): red before
  (`<id> (could not be read)`; the healthchecked control passed), green after.
- **D2637**: `launcher_names` (the install's glob) read by `install_launchers`
  AND the new `check_launchers` (moved out of `check_baseline` first, typed list
  intact, so the test went red on the missing seventh — `5 == 7` — and not on a
  missing function). An empty glob is a DEVIATE, never a clean check (ADR 0195).
  `tests/contract/test_provision_host_launchers.py` runs the REAL
  `install_launchers` unprivileged (`install`'s `-o`/`-g` dropped) against a
  checkout of the six real launchers plus `agentic-postgres-seventh`: 3 tests.
- **D2642**: `resources_created` (D2689); `tests/contract/test_bootstrap_providers.py`
  reuses `test_secret_origin`'s fresh-bootstrap harness: red at session 42
  (`created 4` vs 16), green after; session 2 and the size control pass both.
- **Battery** (`~/s43/run2/battery2.py`, `battery2.txt`): each repair reverted
  alone → its own module FAILED (1, 3, 1), never ERROR; the other two green each
  time; every file restored `cmp`-equal; all three green after. **PASSED.**
- Targeted once (15 modules: the three new, `test_cli_contract`,
  `test_diagnostic_surface`, `test_repository_contract`,
  `test_environment_gates`, `test_acceptance_registry`, `test_evidence_claims`,
  `test_secret_origin`, `test_bootstrap_state`, `test_host_infrastructure`,
  `test_telemetry_admission`, `test_root_script_policy`,
  `test_operator_commands_run_on_the_host`): **1,497 passed, 2 skipped**.
- Committed `95617a8c37bb4ac58ac54ec65e86c932f73abbe7`; **CI `contract` success**
  (run 39369320493).

### Run 3 — the session cookie, the CSRF rule, the invitation link, the QR (`services/auth-api/`, `src/`, `bin/cloud.py`, `contracts/`)

**Read first:** D2656–D2660, D2678; ADRs 0281, 0282 (Run 1's);
`services/auth-api/app/control_routes.py:71-260` (the router, `_caller`,
`_guard`, `_tokens`, the three session routes), `:360-430` (mint, accept);
`services/auth-api/app/control_service.py:234-350` (login, authenticate, the
factor gate), `:370-470`; `services/auth-api/app/models.py:95-150, 521-595`;
`services/auth-api/app/main.py:270-410`; `services/auth-api/app/settings.py`
(how an environment variable becomes a setting — copy the nearest `APG_…`
string setting); `src/agentic_postgres/rendering.py:2230-2250`;
`src/agentic_postgres/naming.py:120-130, 415-440, 1405-1415`;
`services/auth-api/Dockerfile:60-95`; `versions.in.yaml` (the `ARGON2_CFFI_VERSION`
entry) and `bin/lock-versions.sh --help`; the existing tests
`tests/contract/test_control_sessions.py` (how it builds the app and its
cluster — the new module copies that harness), `test_totp.py`,
`test_control_cli.py:280-300, 960-980`.

1. **The console origin, derived once.** `naming.console_origin(project) ->
   str` = `"https://" + <the project's domain as naming already reads it>`
   (find the function `_control_labels` uses for `PROJECT_DOMAIN`); rendering
   emits **`APG_CONSOLE_ORIGIN`** and **`APG_CONSOLE=1`** only where it emits
   `AUTH_APP_MODE=control` (`rendering.py:2239`); the control-mode setting
   `console_origin` reads it (required in control mode, absent elsewhere — a
   control app with no origin refuses to start, the way a missing setting
   already does). `compose.yaml`'s `auth` environment gains
   `APG_CONSOLE_ORIGIN: ${APG_CONSOLE_ORIGIN:-}` beside `:1515`. **Grep every
   reader of the rendered environment for an allowlist** (`grep -rn
   "AUTH_APP_MODE" src tests | head -30`) and add the two names wherever a list
   of rendered variables is asserted (D979).
2. **Cookie mode** (ADR 0281). In `control_routes.py`: a helper
   `_console(request) -> bool` (`request.headers.get("x-apg-console") == "1"`);
   `_tokens` gains a `console` parameter: when true, a `JSONResponse({"expires_at",
   "token_use"})` with two `set_cookie` calls (`key="__Host-apg_access"`, value
   the access token, `max_age=max(1, expires_at - now)`, `httponly=True`,
   `secure=True`, `samesite="strict"`, `path="/"`; `__Host-apg_refresh` with
   `max_age=2592000`); `refresh_session` reads the body if it has one, else —
   in console mode only — `request.cookies.get("__Host-apg_refresh")`;
   `end_session` likewise and, in console mode, answers 204 with both cookies
   deleted (`max_age=0`, the same attributes). **`_caller`**: `Authorization`
   present → today's path; else, if `__Host-apg_access` is present AND
   `_console(request)` AND (method in `GET`/`HEAD` OR `request.headers.get("origin")
   == settings.console_origin`) → authenticate `f"Bearer {cookie}"` through the
   same `authenticate`; a cookie value starting `apg_` → `401`; otherwise today's
   `401`. **A write's Origin check also applies to the three session routes in
   console mode** (a login is a write). Nothing else in `_guard` changes; no CORS
   middleware is added.
3. **The invitation link.** `InvitationResponse` gains `accept_url: str`;
   `mint_invitation` builds it from `settings.console_origin` (D2657). In
   `bin/cloud.py`: `org invite --output` writes `accept_url` (one line, 0600,
   `deliver_secret` unchanged); `read_invitation` accepts the bare token
   (today's regex) **or** a URL whose scheme is `https`, whose path is `/accept`
   and whose fragment is a token matching the same regex — taking the fragment;
   anything else keeps today's message. **Before editing `cloud.py`, wrap its
   import block `:82-88` in the two seam markers** (D2666; Run 6 depends on
   them; a comment-only change here).
4. **The QR** (D2659). `versions.in.yaml` gains `SEGNO_VERSION` (registry
   `pypi`, package `segno`, the version rig 43b read, a comment citing ADR 0282
   and the rig); `bin/lock-versions.sh --update` (read its `--help` for the exact
   verb) regenerates `versions.env` with `SEGNO_VERSION` and its digest;
   `services/auth-api/Dockerfile`'s install `:74-88` gains `"segno==${SEGNO_VERSION}"`
   and the import control `:89` gains `segno`; the build argument is passed
   wherever `ARGON2_CFFI_VERSION` is (`grep -rn "ARGON2_CFFI_VERSION" compose.yaml
   bin src` — every site gains the twin). `FactorEnrolmentResponse` gains
   `otpauth_qr: str`; `begin_factor` adds `segno.make(uri, error="m").svg_data_uri(scale=4)`.
   **The tests run outside the image**: `segno` joins `requirements-dev.in`
   (pinned to the same version) and `bin/lock-dev-deps.sh --update` relocks
   `requirements-dev.txt` with hashes (`test_dependency_lock_uses_hashes`).
5. **The snapshot.** `bin/app-contract.sh --update --snapshot control >
   contracts/control-openapi.canonical.json` (`bin/app-contract.sh:39`; it
   streams to stdout); `git diff --stat` shows only the three members and the
   three routes' descriptions (the `X-Apg-Console` header named in each session
   route's description). `bin/app-contract.sh --check` exits 0.
6. **Tests** — `tests/contract/test_console_session.py` (Docker-backed, the
   `test_control_sessions.py` harness; `pytestmark` first): every node id of
   `CON-SESSION-001`, `CON-CSRF-001`, `CON-INVITE-001` (server half),
   `CON-FACTOR-001` (§2) — the cookie attributes asserted by parsing every
   `Set-Cookie` header (`__Host-` prefix, `HttpOnly`, `Secure`,
   `SameSite=Strict`, `Path=/`, no `Domain`); the body asserted to hold no
   `access_token`/`refresh_token` key; the log canary with a `caplog` of the
   `apg` logger and the request log; the QR decoded **structurally** (an
   `image/svg+xml;base64,` prefix, `<svg` after decoding, no `http`, no
   `<script`) — the optical decode is rig 43b's. `tests/contract/test_control_cli.py`
   gains `test_invite_writes_the_link`, `test_accept_reads_a_token_or_a_link`
   (a link with a path other than `/accept`, an `http` scheme and an empty
   fragment each refused). `tests/contract/test_version_lock.py` gains
   `test_segno_is_locked` beside the existing locked-package tests.
7. **Battery**: (a) drop `httponly=True` → `test_the_console_login_sets_two_host_cookies`
   FAILED; (b) accept a cookie without the header → `test_a_cookie_without_the_header_is_unauthenticated`
   FAILED; (c) skip the `Origin` comparison for writes → `test_a_write_from_another_origin_is_refused`
   FAILED; (d) answer the token in the body too → `…_body_holds_no_token`
   FAILED; (e) build `accept_url` with `?token=` → `test_the_mint_answers_the_accept_url`
   FAILED; **control**: each mutation leaves `test_a_bearer_request_ignores_cookies`
   PASSED (the CLI path is untouched).
8. Targeted: `test_console_session`, `test_control_sessions`, `test_totp`,
   `test_control_cli`, `test_version_lock`, `test_app_contract_aggregate`,
   `test_control_projects`, `test_repository_contract`, `test_environment_gates`,
   the sweep-selector guard. Commit, push, read CI.

**Done.** 2026-10-20 (WSL `~/s43/run3/`). Rows **D2690–D2695**.

- **The origin**: `naming.console_origin(domain)`; rendered `APG_CONSOLE` and
  `APG_CONSOLE_ORIGIN` for every project (`1`/`https://<domain>` on the control
  project only); compose `${APG_CONSOLE_ORIGIN?required}`; read in control mode
  by `settings.load_console_origin()` first in the lifespan, never at build and
  never in `Settings` (D2691).
- **Cookie mode** (ADR 0281) in `control_routes.py`: `_bearer` (one rule, read
  by `_caller` and by `accept_invitation`, D2693), `_console_session_request`
  (a console login, refresh or logout from another `Origin` is 401, D2694),
  `_tokens(console=True)` setting the two `__Host-` cookies and answering
  `{expires_at, token_use}`, refresh/logout reading the refresh cookie from an
  empty body, logout clearing both. The three session routes' descriptions and
  the mint's name the header and the link.
- **The link** (ADR 0282): `accept_url` in the mint answer;
  `org invite --output` writes it (or the bare token from a pre-1.21.0 server,
  D2695); `read_invitation` reads a token or `https://<host>/accept#<token>`;
  `bin/cloud.py`'s import block wrapped in the packaging seam markers.
- **The QR**: `totp.qr_data_uri` (`light="white"`, D2682) →
  `FactorEnrolmentResponse.otpauth_qr`; segno 1.6.6 in `versions.in.yaml` /
  `versions.env` (`--packages-only`, no image moved), the auth Dockerfile
  (install + import control), the three compose build sites, and the dev lock
  at the committed cutoff (D2690).
- **The snapshot** (`bin/app-contract.sh --update --snapshot control`): **two
  members** (`accept_url`, `otpauth_qr`), their two models' descriptions, and
  **four** route descriptions (the three session routes and the mint) — the
  plan said three members and three routes; `--check` passes for both
  snapshots.
- **Tests**: `tests/contract/test_console_session.py` (16: every node id of
  `CON-SESSION-001`, `CON-CSRF-001`, `CON-INVITE-001`'s server half,
  `CON-FACTOR-001`'s two, and `test_a_control_process_without_the_origin_does_not_start`);
  `test_control_cli.py::test_invite_writes_the_link` (the real `org invite` →
  `login accept` with the link file) and `::test_accept_reads_a_token_or_a_link`;
  `test_version_lock.py::test_segno_is_locked`; stricter:
  `test_control_sessions`' log canary plants the QR,
  `test_control_routes_rendered` reads the two keys (`.get`, D2381); widened
  by one named constant: the two compose guards in `test_auth_service_shape`.
- **Battery** (`~/s43/run3/battery3.py`, `battery3.txt`): the plan's five
  (httponly dropped; cookie without the header; no Origin check on writes;
  token in the body; link in the query) and three more (a key rides a cookie;
  the QR without its background; an `http` link accepted) — **8/8 KILLED**,
  each target FAILED, each control PASSED, files restored `cmp`-equal.
- **Targeted** — the first background run was reaped by memory pressure at 44%
  (the laptop, not the tests); re-run in four FOREGROUND shards under `timeout
  570` (`~/s43/shard.sh`; 27 modules). Found and fixed: compose's `:-` default
  (`test_every_setting_is_required_interpolation_or_a_literal`), an `APG_`
  subscript in a test body (`test_environment_gates`, D2381), and a stale
  fixture render read before a later module re-rendered it
  (`test_compose_contract`, green on the current render). Final: shard 1 139+55,
  shard 2 364+20, shard 3 1,227+85, shard 4 46 — all passed.
- Committed `29f0c8de6d50928858d73637b8e11cbb69b0e884`; **CI `contract`
  success** (run 39375323695).

### Run 4 — the console server, its plane and its first pages (`services/console/`, `compose.yaml`, `src/`, `bin/project-runtime.sh`)

**Read first:** D2655, D2661; ADR 0280; `services/docs/serve.py` whole and
`services/docs/Dockerfile` whole; `compose.yaml:1153-1215` (the `docs` service:
limits, user, read-only, healthcheck, networks, labels); `compose.yaml:720-770`;
`bin/project-runtime.sh:105-135`; `src/agentic_postgres/rendering.py:725-745,
2230-2250`; `src/agentic_postgres/runtime_override.py:925-945, 1018,
1505-1545` (how labels reach a service; `_control_labels`); `naming.py:415-440`;
`config.py` (how `DOCS_*` limits are defined — `grep -n "DOCS_" src/agentic_postgres/config.py
src/agentic_postgres/runtime_override.py compose.yaml`); `tests/contract/test_process_limits.py:48-240`;
`tests/contract/test_docs_service.py` (the server's tests, to copy);
`tests/contract/test_reality_ledger.py:245-265`.

1. **`services/console/`**: `Dockerfile` (one stage from `PYTHON_BASE_IMAGE`
   — copy `services/docs/Dockerfile:37-74` minus the bundle stage; `COPY public
   /app/public`; `COPY serve.py /app/serve.py`; uid 65532; the same healthcheck);
   `serve.py` (`services/docs/serve.py`'s structure: `ROUTES` a dict literal of
   every path below to `(file, content type)`; `REDIRECTS = {"/": "/console/",
   "/console": "/console/"}` — **absolute** here, because the console owns its
   host's root, unlike the docs page; `HEALTH_PATH`; the CSP constant from Run
   1's block; `SECURITY_HEADERS` = the docs set with that CSP; `log_message`
   copied); `public/` with `index.html`, `accept.html`, `app.css`, `app.js`,
   `api.js`, `scram.js`, `pages.json`. **Routes**: `/console/` → `index.html`;
   `/accept` → `accept.html`; `/console/app.css`, `/console/app.js`,
   `/console/api.js`, `/console/scram.js`, `/console/pages.json`. **No page
   path beyond these**: the console's views are a fragment router inside
   `index.html` (`#/projects`, `#/projects/<key>/connect`, …), so a reload of
   any view is `/console/`.
2. **The plane.** `compose.yaml` gains `console:` after `docs:` (copy its
   keys: `build` with `PYTHON_BASE_IMAGE`, `image` name pattern, `platform`,
   `pids_limit`/`cpus`/`mem_limit` from `CONSOLE_*`, `read_only: true`,
   `tmpfs` only if the docs service has one, `user: "65532:65532"`,
   `restart`, healthcheck, `networks: [edge]`, the `apg.traefik.scope` label
   pattern) with **`profiles: [console]`**. Limits by ADR 0244's rule from a
   measurement, not a guess: Run 4 builds the image, runs it under a
   1,000-request loop (`curl` of every route), reads `memory.peak` and
   `pids.peak` from its cgroup (the way Session 42 sized the plane), and sets
   memory = max(4 × peak rounded up to 32 MiB, 64), pids = max(4 × peak, 64),
   `cpus` "0.25" (the docs service's value if lower — read it). The defaults
   live where `DOCS_*`'s do (`config.py`), rendered the same way.
   **`bin/project-runtime.sh`**: beside `:127`, `if [ "${APG_CONSOLE:-}" = 1 ];
   then profiles+=(--profile console); fi` (read how `APG_PUBLIC_ENDPOINTS`
   reaches the script and copy that exactly). **The router**:
   `naming.console_router_name(project)` beside `:420-428`; a
   `_console_labels` in `runtime_override.py` copying `_control_labels`
   (`:1508-1544`) — the rule ``Host(`<domain>`) && (Path(`/`) ||
   Path(`/accept`) || PathPrefix(`/console/`))``, entrypoint `websecure`, the
   baseline chain **without** the buffering and strip middlewares, the service
   port 8080 — attached to the `console` service's labels only when the project
   is the control project.
3. **The first pages** (onboarding and sign-in): `accept.html` (+ the shared
   `app.css`, `api.js`, `scram.js`): read the fragment, `replaceState`, show
   *"Create your account"* (username, display name, password twice) → `POST
   /v1/invitations/accept` → `POST /v1/sessions` (console mode) → `GET /v1/me`
   → if `second_factor.required && !enabled`: `POST /v1/me/totp` → show
   `<img src=otpauth_qr>` and the `secret` text → a code field → `POST
   /v1/me/totp/confirm` → (sessions ended) `POST /v1/sessions` with the code →
   `location.assign("/console/")`. A signed-in visitor holding a membership link
   sends the token alone (the route's other form). `index.html`: sign-in
   (username, password, code if `second_factor_required`), sign-out, and the
   Overview (`GET /v1/me`, `GET /v1/organizations`, `GET /v1/projects?organization=`).
   **`api.js`** is the only file that calls `fetch`: every call sends
   `X-Apg-Console: 1`, `credentials: "same-origin"`, JSON; a `401` triggers one
   `POST /v1/sessions/refresh` and one retry (the CLI's rule,
   `control_client.py:412-469`), then the sign-in view; the refusal's one word is
   shown with the sentence `docs/control-plane.md` gives it. **No `innerHTML`
   with any server value** — every value set with `textContent` (a test greps
   `innerHTML` and `insertAdjacentHTML`, allowed only on string literals).
   `pages.json` lists every view with its Ledger rows and the `operationId`s it
   calls (Run 5 completes it).
4. **The guard** (ADR 0280): `tests/contract/test_reality_ledger.py::test_no_console_exists_yet`
   is **deleted and replaced** by `test_every_console_page_maps_to_a_reachable_row`
   (reads `services/console/public/pages.json`: every view names ≥ 1 row, every
   row exists and is in `REACHABLE` — **`console` itself is `planned` until Run
   9**, so until then the test reads `pages.json`'s rows **excluding the
   `console` row's own name** and asserts the console row is `planned` with
   `target_session: 43`; Run 9 removes that exception in the same commit that
   moves the row — D690's all-or-nothing). New modules
   `tests/contract/test_console_server.py` (the server in-process, the
   `test_docs_service.py` pattern), `tests/contract/test_console_plane.py`
   (`compose config` with and without `APG_CONSOLE=1`, the render of
   `project.control.example.yaml` and of `project.example.yaml` — the console
   service and its router present in the first only), `test_process_limits.py`
   gains `test_the_console_is_bounded`, and `tests/contract/test_console_pages.py`
   (every `api.js` call's path, normalised `{…}`, is a path in the snapshot; no
   `localStorage`/`sessionStorage`/`indexedDB`/`document.cookie` write in any
   script; no `innerHTML` with a non-literal; no string matching
   `\b(select|insert|update|delete|create|drop|alter)\s` case-insensitively
   outside comments — `test_no_script_holds_sql`).
5. **The render that every gate reads** (D1507): the four renders and the
   control project's — Run 4 runs `bin/apg.sh generate --check --project
   project.example.yaml` and the control example's render and deletes what it
   published under `.generated/<key>` (CLAUDE.md §1).
6. **Battery**: add a route `/console/x` serving `/etc/passwd`'s path string →
   `test_only_the_listed_paths_answer` FAILED; drop `frame-ancestors` →
   `test_every_answer_carries_the_policy` FAILED; add the profile for every
   project → `test_the_profile_is_added_only_for_the_control_project` FAILED;
   add `<script src="https://cdn.example/x.js">` to `index.html` →
   `test_every_asset_is_our_own_file` FAILED; **control**: `test_docs_service`
   PASSED throughout.
7. Targeted: the four new/changed console modules, `test_reality_ledger`,
   `test_process_limits`, `test_docs_service`, `test_container_selectors`,
   `test_repository_contract`, `test_cli_contract`, `test_environment_gates`,
   the sweep-selector guard. Commit, push, read CI.

**Done.** 2026-10-20 (WSL `~/s43/run4/`). Rows **D2696–D2701**.

- **`services/console/`**: `serve.py` (the seven file routes, `/console/env.json`
  → the API path from `APG_CONSOLE_API_PATH` (D2697), the two redirects, the
  health path; ADR 0280's CSP and the docs headers added in `end_headers`, so a
  501 carries them too (D2700); `log_message` without the query); `Dockerfile`
  (one stage from `PYTHON_BASE_IMAGE`, `public/` and `serve.py`, uid 65532,
  the docs healthcheck); `public/`: `index.html`, `accept.html` (no inline
  script), `app.css`, `api.js` (the only `fetch`: `X-Apg-Console`,
  same-origin, `redirect: "error"`, one refresh-and-retry on 401), `app.js`
  (the accept flow — fragment read and `replaceState` before the first request;
  create account → console sign-in → factor enrolment from the server's QR →
  sign in with the next code — sign-in with the code field on
  `second_factor_required`, sign-out, the overview), `scram.js` (32-byte
  password, D2698; its proof is Run 5's), `pages.json` (three views:
  `accept`, `sign-in`, `overview`).
- **Measured** (`~/s43/run4/measure.txt`): image 43,209,566 B; at rest
  28.6 MB; 1,008 requests in 14.2 s → `memory.peak` 44.07 MiB, `pids.peak` 8;
  healthy. **Limits 192 MiB / 64 / 0.25** (D2699).
- **The plane**: `compose.yaml` `console` (`profiles: [console]`, `CONSOLE_*`,
  read-only, `cap_drop: ALL`, `edge` only, no mount, no secret);
  `config.py`, `rendering.py` (`CONSOLE` in `SERVICE_RESOURCE_ORDER`,
  `CONSOLE_MEMORY_LIMIT`, `CONSOLE_ROUTER_NAME`); `naming.CONSOLE_SERVICE`,
  `naming.console_router_name`; `runtime_override._console_labels` (the
  three-path rule, the baseline chain only, port 8080) when `console`;
  `bin/deploy-project.py::_override_console` at both override sites;
  `bin/project-runtime.sh` adds `--profile console` on `APG_CONSOLE=1`.
- **The guard** (ADR 0280): `test_no_console_exists_yet` → 
  `test_every_console_page_maps_to_a_reachable_row` (the `console` row's own
  name excluded until Run 9, asserted `planned`/43); `LEDGER-001`'s node id
  moved in the registry, the acceptance matrix regenerated.
- **Tests**: `test_console_server.py` (7 — the real server in a thread, asked
  over HTTP: the closed table, the policy on 200/301/404/HEAD/501, the env
  answer, the log, every asset our own, GET/HEAD only, the image),
  `test_console_plane.py` (3 — two real renders through `project-runtime.sh`'s
  `session_profiles` and the deploy's `_override_*`), `test_console_pages.py`
  (6 — calls ⊆ snapshot and = `pages.json`, rows reachable, no SQL (D2696),
  no storage, no markup sink, only `api.js` fetches),
  `test_process_limits.py::test_the_console_is_bounded`; four counting guards
  widened to the measured set (D2699); `BUILT_SERVICE_USERS` gains `console`.
- **Renders**: the control example and `project.example.yaml` render and
  validate in a temporary root (`~/s43/run4/renders.py`: `APG_CONSOLE` 1/0, the
  origin on the control project only); `apg generate --check` exit 0; the two
  fixture renders refreshed (`~/s43/rerender.sh`, 6 console keys each).
- **Battery** (`~/s43/run4/battery4.py`): the plan's four (a route to
  `/etc/passwd`; `frame-ancestors` dropped; the profile for every project; a
  third-party script) and two more (markup from a value; a call outside the
  snapshot) — **6/6 KILLED**, `test_docs_service` (33) PASSED each time.
- **Targeted**, foreground shards: A (13 modules) and B (18) — found and fixed:
  `bin/project-runtime.sh`'s executable bit lost through `\\wsl$`
  (`test_cli_contract`), an `APG_` subscript in a test body (D2381), and
  `BUILT_SERVICE_USERS` — then **1,262 + 857 and 592 + 85 passed**.

### Run 5 — the console's customer pages (`services/console/public/`, the Ledger row's text)

**Read first:** Run 4's files; `contracts/control-openapi.canonical.json` (each
route's request and answer shapes); `bin/cloud.py` for each family's behaviour
the page mirrors (credential rotation `:990-1010`, project creation
`:1160-1200`, export `:840-870` area — `grep -n "def cmd_\|def do_" bin/cloud.py`);
`docs/managed-projects.md` (what each refusal means, `:337-349`).

**The views** (each a fragment route in `index.html`, each a `pages.json`
entry with its rows and `operationId`s; `GET` views poll nothing — a *Refresh*
button; an operation started shows `GET /v1/operations/{id}` every 2 s until a
terminal state, the way `apg operation wait` does):

| View | Calls | Ledger rows |
|---|---|---|
| Overview `#/` | `GET /v1/me`, `GET /v1/organizations`, `GET /v1/projects` | `accounts`, `organizations`, `projects_self_service` |
| Create organisation / project `#/new` | `POST /v1/organizations`, `POST /v1/projects` (both verifiers from `scram.js`; the two passwords shown once) | `organizations`, `projects_self_service`, `region`, `compute_profiles` |
| Connect `#/projects/<k>/connect` | `GET …/connections`, `POST …/credentials` (verifier only; the new password shown once, with the pooled and direct strings and a `psql` line built from them) | `pooled_endpoint`, `direct_endpoint`, `postgresql` |
| Branches `#/projects/<k>/branches` | `GET/POST …/branches`, `GET …/branches/{b}`, `POST …/reset`, `DELETE …/branches/{b}`, `POST …/restores` | `branches`, `restore_to_branch` |
| Backups `#/projects/<k>/backups` | `GET …/backups` | `backups_and_pitr` |
| Usage `#/projects/<k>/usage`, `#/org/<o>/usage` | `GET …/usage` (both) | `usage` |
| Insights `#/projects/<k>/insights` | `GET …/insights?hours&limit` (the numbers and the `tuning` sentence; `could_not_determine` shown as such) | `query_insights` |
| Monitoring `#/projects/<k>/monitoring` | `GET …/monitoring` (each reading with its source) | `monitoring` |
| Plan `#/org/<o>/plan` | `GET /v1/plans`, `GET …/plan`, `POST …/plan-interest` (*Notify me*) | `plan_free`, `plan_premium` |
| Notifications `#/org/<o>/notifications` | `GET …/notifications` | `notifications` |
| Settings `#/org/<o>/settings` | members (`GET`, `PATCH`, `DELETE`), invitations (`POST /v1/invitations` — the link shown once with a *Copy* button; `GET`, `DELETE`), keys (`GET`, `POST` — the key shown once; `DELETE`) | `organizations`, `api_keys`, `accounts` |
| Project settings `#/projects/<k>/settings` | `PUT …/idle-sleep`, `PUT …/compute`, `POST …/sleep`, `POST …/wake`, `POST …/export` (the download link shown once from the operation), `DELETE /v1/projects/{k}` (typed confirmation: the key) | `idle_sleep`, `compute_profiles`, `sleep`, `export`, `project_deletion` |

**Rules every view keeps** (each held by `test_console_pages.py`): a secret
(a password, a key, an invitation link, an export link) is rendered once into a
`<code>` element with a *Copy* button and dropped from the view's state when the
view is left; **no secret in a URL, a fragment route or storage**; a refusal
shows its one word and the sentence; a planned feature has no control (the
guard). **The `console` row's `stage5_reality`** is rewritten to D2661's
sentence in `docs/reality-ledger.yaml:196-211` and `bin/render-reality-ledger.py
--write` regenerates the page.

**Tests**: `pages.json` complete (every `operationId` the views call; the guard
checks each against the snapshot); `test_console_scram.py` (Docker-backed:
`docker run --rm -v <public>:/c:ro <NODE_BASE_IMAGE> node --input-type=module -e
"import {verifier} from '/c/scram.js'; …"` with a fixed password and a fixed
salt passed in base64 — `scram.js` exports `verifier(password, saltBytes)` for
exactly this — equal to `scram.verifier(password, salt=…)`; **control**: a
different salt differs). Battery: change the iteration count to 4,095 →
`test_the_browser_verifier_equals_the_clis` FAILED; add a view calling
`/v1/ledger` → `test_every_called_path_is_in_the_snapshot` FAILED; add a view
naming `sql_editor` → `test_no_page_names_an_unreachable_row` FAILED; control:
`test_console_server` PASSED.

Targeted: the console modules, `test_reality_ledger`, `test_documentation_index`.
Commit, push, read CI.

**Done.** 2026-10-20 (WSL `~/s43/run5/`). Rows **D2702, D2703**.

- **The views** (`services/console/public/app.js`, one file, fragment routes):
  the overview (organisations, their projects, links), `#/new` (create an
  organisation), and per project **Connect** (the two doors' strings; a new
  password for `customer_app` or `customer_admin` made in the page, only its
  verifier sent, the operation followed every 2 s, then the password, the
  string with it and a `psql` line shown once), **Branches** (list; create or
  restore-to with two passwords made in the page and shown once; reset; delete
  with the name typed), **Backups**, **Usage**, **Insights** (the numbers and
  the server's tuning sentence; *could not be determined* shown as such),
  **Monitoring** (each reading with its source), **Settings** (idle sleep,
  resize, sleep, wake, export — the download link shown once — and delete with
  the key typed); per organisation **Plan** (*Notify me* for a plan not
  active), **Usage**, **Notifications**, **Members and keys** (role change,
  removal, an invitation link shown once with *Copy*, revocation, a key shown
  once). Every refusal shows its word and a sentence. **No project-creation
  view** (D2702, the operator's choice). `pages.json`: 15 views, every call
  and every row.
- **The Ledger**: `console.stage5_reality` rewritten (D2661's sentence plus
  *"A project is created with the command-line client in this beta"*); the
  `agents`, `workflows`, `connectors`, `audit` rows no longer say the console
  reaches them through Studio (D2703); `docs/reality-ledger.md` regenerated.
- **Tests**: `test_console_scram.py` (3, Docker-backed in `NODE_RUNTIME_IMAGE`,
  `--network none`: the verifier byte-equal to `scram.verifier` for two salts,
  the password's shape, `node --check` of every script); the page guard's call
  reader also reads `operate(...)`; the asset guard reads only `import`
  statements (it had matched the words *"Restorable from "*).
- **Battery** (`~/s43/run5/battery5.py`): the plan's three (4,095 iterations;
  a view calling `/v1/ledger`; a view naming `sql_editor`) and two more (a
  syntax error in `app.js`; a password written to `localStorage`) — **5/5
  KILLED**, `test_console_server` (7) PASSED each time.
- **Targeted** (foreground): 11 modules, **417 passed**.
- Pushed with Run 4 in one push; Run 4's verdict is read at this run's SHA,
  which contains it.

### Run 6 — the packaged CLI and its publish workflow (`bin/cloud.py`, `bin/build-cli.py`, `.github/workflows/publish-cli.yml`)

**Read first:** D2652, D2666, D2667; ADR 0284; rig 43d's readings;
`bin/cloud.py:60-100` (the seam Run 3 marked), `:1290-1310` (`INTEREST_PLANS`
and its use — `grep -n "INTEREST_PLANS" bin/cloud.py`), `:1500-1560`,
`:1780-1799`; `tests/contract/test_control_cli.py:960-980` and every test that
names `INTEREST_PLANS` or `notify-me`; `.github/workflows/ci.yml` whole (the
action pins and the uv setup to copy); `tests/contract/test_gate_contract.py:150-330`
(what it reads in every workflow); `tests/contract/test_cli_contract.py:288-310`
(`PYTHON_COMMANDS`).

1. **`plans` leaves `cloud.py`.** Remove `plans` from the import block; replace
   `INTEREST_PLANS` and the parser's `choices=` with: the `notify-me` verb takes
   any name, calls `GET /v1/plans` through the session, and refuses locally with
   today's message when the name is absent or its `status` is `active`; then
   posts as today. Re-point the test(s) that read `INTEREST_PLANS` (D1119).
   **`--version`** on the top-level parser prints `apg <VERSION>` — read from
   `REPO_ROOT / "VERSION"` inside the seam (the staged copy replaces it with
   `apg_cli.__version__`). Every other line of `cloud.py` stays.
2. **`bin/build-cli.py --out DIR`** (imports `agentic_postgres` and the
   standard library only, ADR 0093): refuses a `DIR` inside the repository
   (exit 2) or one that exists and is not empty (exit 2); stages
   `DIR/src/apg_cli/` exactly as D2666 lists — `cli.py` is `bin/cloud.py` with
   the text between the two seam markers replaced by a fixed block (three
   imports and `__version__`), **and the run fails (exit 3) if the markers are
   not found exactly once each**; `control_client.py` and `scram.py` copied
   byte-for-byte; `__init__.py` (`__version__ = "<VERSION>"`); `__main__.py`
   (`from apg_cli.cli import main; raise SystemExit(main())`); `DIR/pyproject.toml`
   (D2666's fields; the build backend `setuptools` at the version the root
   `pyproject.toml` already requires, `:7-9`, so no new backend enters);
   `DIR/README.md` (generated from `site/pages/docs/cli.md` by the site
   renderer's text mode — or a fixed paragraph and the site's URL if Run 7 has
   not landed; the run says which); `DIR/LICENSE` copied from the repository's
   licence file (read its name at the root first; **if the repository has none,
   §9's stop** — a public package needs the operator's licence decision). Then
   runs `uv build --sdist --wheel --out-dir DIR/dist DIR` (uv found on `PATH`;
   absent → exit 4 with the sentence). Prints the two artefacts' names and
   sha256. Registered in `PYTHON_COMMANDS` (`test_cli_contract.py:288-`), `git
   add`ed before the test (D1014).
3. **`.github/workflows/publish-cli.yml`** exactly as D2667 (the `verify` step a
   short inline script reading `gh api` JSON with `jq` — the three buckets
   spelled out; `VERSION` compared to `${GITHUB_REF_NAME}`); every action pinned
   by commit SHA as `ci.yml` pins its own (copy those SHAs for checkout,
   setup-python, setup-uv, upload/download-artifact); `pypa/gh-action-pypi-publish@<sha>`
   from rig 43d; `concurrency: {group: publish-cli, cancel-in-progress: false}`.
4. **Tests** — `tests/contract/test_cli_package.py` (`pytestmark` first;
   Docker-backed for the install): stage into `tmp_path`; diff each staged file
   against its source (only the seam differs; the copies byte-equal);
   `ast`-walk every staged module's imports (stdlib per
   `sys.stdlib_module_names`, or `apg_cli`); build; `docker run --rm --network
   none -v <dist>:/dist:ro <PYTHON_BASE_IMAGE> sh -c "pip install --no-index
   /dist/*.whl && apg --version && for f in login logout context org project
   compute operation endpoint branch plan usage notifications insights
   monitoring; do apg $f --help >/dev/null || exit 1; done"` — **written to a
   script file inside `tmp_path`**, never an inline `for` through two shells
   (CLAUDE.md §1). `tests/contract/test_release_workflows.py` (`yaml.safe_load`
   of both workflows; Run 7 adds the site's half): D2667's four node ids.
5. **Battery**: put `from agentic_postgres import plans` back inside the seam's
   replacement → `test_the_package_imports_only_stdlib` FAILED; change one line
   of `cli.py` outside the seam in the stage → `test_the_stage_differs_only_in_the_seam`
   FAILED; give the `build` job `id-token: write` →
   `test_only_the_publish_job_has_id_token` FAILED; replace the action's SHA with
   a tag → `test_publish_pins_the_action` FAILED; **control**:
   `test_control_cli` PASSED throughout.
6. Targeted: `test_cli_package`, `test_release_workflows`, `test_control_cli`,
   `test_cli_contract`, `test_gate_contract`, `test_repository_contract`,
   `test_environment_gates`, the sweep-selector guard. Commit, push, read CI.
   **The publish workflow does not run** (no tag) — `gh api …/actions/runs?head_sha=`
   lists only `contract` for this SHA, and that is the expected reading.

**Done.** 2026-10-20 (WSL `~/s43/run6/`). Rows **D2704–D2707**.

- **`LICENSE`** at the root: the Apache License 2.0, fetched unmodified from
  apache.org (202 lines, sha256 `cfc7749b…3d30`) — the operator's choice
  (D2685); §9's stop cleared.
- **`bin/cloud.py`**: `plans` left (the `notify-me` verb reads `GET /v1/plans`
  and refuses an absent or active name locally with exit 2 — the existing
  `--plan free` proof unchanged); the seam carries `__version__`, `PROG`,
  `COMMAND` (D2704); `--version` → `apg 1.20.0`, exit 0.
- **`bin/build-cli.py --out DIR`** (registered in `PYTHON_COMMANDS`): refuses
  an `--out` inside the repository or not empty (2), seam markers not exactly
  once (3), no uv or a bad build (4). Staged at `/tmp/s43-cli2`:
  `src/apg_cli/__init__.py` 76 B, `__main__.py` 55, `cli.py` 80,195,
  `control_client.py` 19,147, `scram.py` 2,299; `pyproject.toml`, `README.md`
  (the fixed paragraph, D2705), `LICENSE`. Built:
  `agentic_postgres_cli-1.20.0-py3-none-any.whl` sha256 `566112da…76fd`,
  `agentic_postgres_cli-1.20.0.tar.gz` `42f671f9…680a` (a build is not
  byte-reproducible — timestamps; the release's own is CI's).
- **`.github/workflows/publish-cli.yml`**: tag `[0-9]+.[0-9]+.[0-9]+` only;
  `permissions: {}`; `verify` (tag = `VERSION`; the latest `contract` run
  succeeded, D2707) → `build` (`contents: read`) → `publish` (environment
  `pypi`, `id-token: write` only there); every action by SHA (D2706). It does
  not run in this run (no tag).
- **Tests**: `test_cli_package.py` (5 — the stage differs only in the seam;
  stdlib-only imports; the version; `--out` refusals; the wheel installed with
  `--network none` into `PYTHON_RUNTIME_IMAGE`, `apg --version` and all
  fourteen families' usage equal to the tree's), `test_release_workflows.py`
  (D2667's four node ids, the verify step executed in 7 cases, and the tag
  rule).
- **Battery** (`~/s43/run6/battery6.py`): the plan's four (`plans` back in the
  staged seam; a line outside the seam changed; `id-token` on the build job;
  the action by tag) and one more (an empty list passes) — **5/5 KILLED**, the
  control (`test_control_cli::test_accept_reads_a_token_or_a_link`) PASSED.
- **Targeted** (foreground): `test_cli_contract` 841; 8 modules 428 — all
  passed.

### Run 7 — the site, its build, its workflow, the customer documentation (`site/`, `src/`, `bin/build-site.py`, `.github/workflows/site.yml`, `docs/`)

**Read first:** D2651, D2653, D2654, D2662–D2664, D2674, D2676; ADR 0283; rig
43c's readings; `src/agentic_postgres/reality_ledger.py` whole;
`services/auth-api/app/plans.py` whole; `docs/managed-projects.md` whole;
`docs/control-plane.md:110-311`; `docs/monitoring.md:1-75`;
`docs/database-connections.md:65-110`; `docs/README.md` (the index, to keep
every link valid); `tests/contract/test_documentation_index.py:440-490`.

1. **`src/agentic_postgres/site_build.py`**: the subset renderer (D2663), the
   page model (front matter → `title`, `ledger`, `description`), the guards
   (D2662's refusals, `FORBIDDEN_WORDS` via `reality_ledger.forbidden_words_in`
   — read its signature at `:206`), the pricing body (D2664), the Ledger page
   (D2674), the layout (one `site/templates/base.html` with `{{title}}`,
   `{{description}}`, `{{nav}}`, `{{body}}`, `{{digest}}` — substitution only,
   the rendering convention of ADR 0002's tree), **the build digest** = sha256
   over the sorted (path, bytes) of every input — `site/**`, `services/auth-api/app/plans.py`,
   `docs/reality-ledger.yaml`, `VERSION` — emitted as `<meta name="apg-site-digest"
   content="…">` in every page (the external proof `SITE-LIVE-001` recomputes it
   from the evidence commit's tree). Constants: `INVITATION_ADDRESS
   = "invite@agenticpostgresql.com"`, `CONSOLE_URL =
   "https://control.agenticpostgresql.com/console/"`, `CONTROL_ENDPOINT =
   "https://control.agenticpostgresql.com/api/v1"` — **each asserted equal to
   what `naming` derives for `project.control.example.yaml`'s domain** where
   naming can derive it (the endpoint and the console origin), so the site
   cannot drift from the product's names.
2. **`bin/build-site.py --out DIR [--check]`** (imports `agentic_postgres` and
   `yaml` only): refuses an `--out` inside the repository; writes every page as
   `DIR/<path>/index.html` (pretty URLs: `/docs/connecting/`), `DIR/site.css`,
   `DIR/_headers` (D2676's rule with the site's CSP and the docs server's other
   headers, `Cache-Control: public, max-age=300` for the pages), `DIR/404.html`;
   `--check` builds twice and compares. Exit codes: 0, 2 (usage), 3 (a page
   refused — the file, line and reason printed). Registered in
   `PYTHON_COMMANDS`.
3. **The pages** (`site/pages/`, D2662's list). Written fresh for a stranger
   from the customer sections of `managed-projects.md`, `control-plane.md`,
   `monitoring.md` and `database-connections.md:69-108`: every command as `apg
   <family> <verb> …` with the flags `bin/cloud.py --help` prints for it (the
   run reads each `--help` and the page copies the flags, never memory); the
   quickstart is *install the CLI or open the console → accept your invitation
   → enrol your authenticator → create or open a project → Connect*; every page
   ends with *"Something here wrong or missing? Write to invite@…"*. The landing
   page: what the product is in three sentences that the Ledger backs, the beta
   sentence, *Request an invitation* (`mailto:` with a subject), links to the
   docs, the console and the Ledger. **No page names a feature whose row is not
   reachable** (the build refuses). `site/templates/base.html`, `site/static/site.css`
   (system fonts only, no font file — D2596's *self-hosted* is met by having
   none).
4. **The repository's documents**: `docs/managed-projects.md` becomes the
   pointer (D2662); the customer halves of `control-plane.md` and
   `monitoring.md` become one sentence each pointing to `site/pages/`; **every
   reader of a moved section is grepped first** (`grep -rn "managed-projects.md#\|managed-projects.md)"
   docs README.md src bin tests`) and re-pointed; `docs/README.md` gains a line
   for `site/` under *Start here*. `docs/control-plane.md:308-311`'s *"no web
   console"* is corrected to name the console (Run 4) — **this run's text, so the
   row is honest at the commit the site goes live**.
5. **`.github/workflows/site.yml`** exactly as D2653; the Pages project name
   `agentic-postgres-site`; `wrangler@<version from rig 43c>`; `environment:
   site`; `permissions: contents: read`; actions pinned by the same SHAs as
   `ci.yml`. `tests/contract/test_release_workflows.py` gains D2653's two node ids.
6. **Tests** — `tests/contract/test_site.py` (`pytestmark` first): every node id
   of `SITE-BUILD-001` and `SITE-CLAIM-001` (§2) — builds into `tmp_path`; the
   pricing test monkeypatches a copy of `PLANS`' free `projects_active` to 7 and
   finds `7` in the page and the original value gone; the third-party scan reads
   every `src=`/`href=` in the built HTML and CSS (relative, `#`, `mailto:invite@…`,
   or `https://` to exactly the apex, `www`, `control.agenticpostgresql.com`, or
   `github.com/Virabyan99/agentic-postgres` — nothing else); the host-address
   scan finds no `15.204.`, no IPv4 literal, no `*.slot`/`pool.`/`direct.` name
   in the build or the workflow.
7. **Battery**: add a page naming `sql_editor` → `test_every_page_names_reachable_rows`
   FAILED; write `$5/month` into `pricing.md` → `test_no_price_is_printed`
   FAILED; add `<img src="https://example.com/x.png">` via a raw HTML line →
   `test_raw_html_is_refused` FAILED; add `sudo` to `connecting.md` →
   `test_no_page_holds_an_operator_command` FAILED; **control**:
   `test_reality_ledger` PASSED throughout.
8. Targeted: `test_site`, `test_release_workflows`, `test_reality_ledger`,
   `test_documentation_index`, `test_session12_documented_path`,
   `test_gate_contract`, `test_cli_contract`, `test_repository_contract`,
   `test_environment_gates`, the sweep-selector guard. Commit, push, read CI —
   **and then the `site` workflow's run for the same SHA**. Its first run
   creates the Pages project's first deployment on `agentic-postgres-site.pages.dev`
   (if the project does not exist, wrangler creates it — rig 43c recorded
   whether it does; if it does not, the agent creates it through the API with
   production branch `main` before the push).
9. **Sheet C4 (the agent)**: attach `agenticpostgresql.com` and
   `www.agenticpostgresql.com` to `agentic-postgres-site` (`POST
   /accounts/{account}/pages/projects/agentic-postgres-site/domains`, one each),
   read each domain `active` (the certificate takes minutes; read every 60 s up
   to 30 min, **never a retry loop on a failure** — a failure is recorded and
   the operator asked), read the two records Cloudflare created (`proxied:
   true`) and **every A record still `proxied: false`**; `curl -sI
   https://agenticpostgresql.com/` and `https://www.agenticpostgresql.com/` →
   200 with the CSP; `/docs/connecting/` 200; `/missing` 404.

**Done.** 2026-10-20 (WSL `~/s43/run7/`). Rows **D2708–D2712**.

- **`src/agentic_postgres/site_build.py`** (the subset, the guards, the
  generated pricing and Ledger bodies, the layout, `_headers`, the digest) and
  **`bin/build-site.py`** (registered; `--out`, `--check`; exit 2/3/5).
  `CONTROL_ENDPOINT` and `CONSOLE_URL` are `naming`'s derivations, asserted.
- **The pages** (`site/pages/`, 13) and their rows: `/` (accounts,
  organizations, projects_self_service, postgresql, pooled/direct_endpoint,
  branches, backups_and_pitr, plan_free), `/quickstart/`, `/pricing/`
  (plan_free, plan_premium — generated), `/ledger/` (every row — generated),
  `/docs/` and `getting-started`, `projects` (D2709), `connecting`,
  `branches`, `backups`, `plans-and-usage`, `insights-and-monitoring`, `cli`,
  `refusals`; every command copied from the CLI's usage (`~/s43/run7/usage.txt`);
  every page ends with the invitation address. 17 files; two builds
  byte-equal; digest at this commit printed by `bin/build-site.py --check`.
- **Documents**: `managed-projects.md` the pointer; `control-plane.md` and
  `monitoring.md` cut (D2709); `docs/README.md` names the site; the Ledger's
  `management_api` sentence corrected (D2712).
- **`.github/workflows/site.yml`** (D2653): `workflow_run` of `contract` on
  `main`, success and push only, checks out `head_sha`, builds, `npx --yes
  wrangler@4.147.0 pages deploy … --project-name agentic-postgres-site
  --branch main`, environment `site`; the Pages project created first (D2711).
- **Tests**: `test_site.py` (20: every node id of `SITE-BUILD-001` and
  `SITE-CLAIM-001`, plus the published names and the command's refusals);
  `test_release_workflows.py` gains D2653's two.
- **Battery** (`~/s43/run7/battery7.py`): **5/5 KILLED**, `test_reality_ledger`
  (13) PASSED each time (D2710).
- **Targeted** (foreground): 11 modules **1,338 passed**; the documentation
  guards 899.

### Run 8 — the trip's instruments, written and rehearsed offline

**Read first:** D2668, D2669, D2671, D2675; `~/s42/run8/` and `~/s42/run10/`
(every instrument there, as the shapes to derive from: `s42-window.py`,
`s42-x0b.sh`, `s42-external.sh`, `s42-sweep.sh`), `~/s42/run11/NOTES.md`;
`tests/external/test_session42_reearning.py` (the external proof shape,
`test_this_module_uses_no_ssh`); `tests/external/redaction.py`; the Session 39
customer-connection fixture (`grep -n "verify-full\|sslmode" tests/external/*.py`);
`~/s37/` (the probe's files: `probe.json`, `probe-password`, `probe-otpauth`).

1. **`tests/external/browser/console_walk.py`** (in the tree; never collected:
   no `test_` prefix, and `pytest.ini`'s `testpaths` reads it only as a module
   nobody imports — **Run 8 confirms with `pytest --collect-only -q tests/external`
   that it is not collected**). Arguments: `--link-file F` (the 0600 file `apg
   org invite` wrote), `--record R`, `--password-out P` (0600; the rotated
   password, for the proof and the creds copy), `--project slot3-prod`,
   `--dry` (stop before the rotation). It: opens a fresh context; reads FCP on
   `/console/` three times in fresh contexts (D2675); opens the link; asserts the
   address bar no longer holds the token after load (`page.url` has no `#`);
   creates the account (`walk-s43-<6 hex>`, a 24-byte random password held in a
   variable); reads `/v1/me` through the page; enrols (reads the base32 text,
   computes TOTP with `hmac`/`hashlib`/`struct` — RFC 6238, SHA-1, 30 s, 6
   digits — and **waits for a fresh window if fewer than 5 s remain**); confirms;
   signs in with a new code; reads the two cookies from the context
   (`context.cookies()`: names, `httpOnly`, `secure`, `sameSite`; **never
   values**); opens Connect; rotates `customer_app`; waits for the operation;
   reads the pooled string and the password once; reloads and asserts the
   password text is absent; writes the record (steps, times, cookie flags, the
   console's response headers for `/console/` and `/accept` — CSP, frame,
   referrer, nosniff). **The record holds no secret** (a self-check before the
   write: the record's JSON must not contain the password, the seed, the
   invitation token, or the cookie values — the instrument exits 6 if it does).
2. **`tests/external/test_session43_console.py`** (`pytestmark` first; reads
   `os.environ.get("APG_CONSOLE_RECORD_FILE")` and the existing control-outputs
   gate): every external node id of `CON-LIVE-001`, `CON-LIVE-002`,
   `SITE-LIVE-001` (§2). **The live CSRF readings are taken by the driver
   with the walker's REAL session and recorded as statuses only** — Playwright's
   `context.request` shares the browser context's cookies, so no cookie value
   leaves the context: (a) `context.request.get(".../api/v1/me")` **without**
   `X-Apg-Console` → expected 401; (b) `context.request.delete(".../api/v1/sessions/current",
   headers={"X-Apg-Console": "1", "Origin": "https://evil.example"})` →
   expected 401; (c) then `GET /api/v1/me` from the page (header, right origin)
   → 200 — the session survived the forged sign-out (**the control**); (d) the
   real sign-out from the page at the walk's end → 204 and both cookies gone
   from `context.cookies()`. `test_a_cookie_alone_is_refused_live` and
   `test_a_foreign_origin_write_is_refused_live` read (a)–(d); the proof itself
   also sends one `httpx` request with a forged `__Host-apg_access=x` and the
   header → 401. **This is why the walk signs out last**: W1's record is
   written after (d). The site
   proofs read the apex and `www` with `httpx`, recompute the build digest from
   the tree at the evidence commit (`site_build.input_digest()`), and read every
   asset URL the pages name (only the apex, `www`, `control.`, `github.com/Virabyan99/…`).
   The connection proof reads `--password-out`'s file through `Secret`, connects
   with `psycopg` to the pooled name with `sslmode=verify-full`, `SELECT 1`.
3. **`tests/deployment/test_session43_console_host.py`** (host; `pytestmark`
   first): `CON-HOST-001`'s three node ids, through the deployed document and
   `docker inspect` the way Session 42's host module reads the plane.
4. **The trip's scripts** in WSL `~/s43/run8/`, each derived from its Session
   42 twin by diff (never retyped): `s43-window.py`, `s43-x0.sh` (exports
   `TMPDIR=~/s43/tmp`, D2644), `s43-walk.sh` (pulls the Playwright image by
   digest; runs `org invite` as the probe owner into a 0600 link file; runs the
   driver in the container with the checkout mounted read-only at `/repo`, the
   output directory read-write, `--network host`; then copies the creds file to
   `.before-s43` and writes the new one; then the probe owner's `apg org remove`
   of the walker), `s43-sweep.sh`, `s43-external.sh` (adds
   `--console-record-file`), `s43-after.sh` (the post-deploy reading: every
   project's doctor, the console container, the listeners).
5. **Rehearsed offline**: the driver against the console image served locally
   (`docker run -p 127.0.0.1:18080:8080 <console image>`) with **every `/api/v1`
   call answered by Playwright's `page.route` from fixtures** (a fixture per
   route the walk calls, shaped from the snapshot) — the DOM path, the TOTP
   timing, the record's self-check (a fixture that leaks the password into a
   page attribute → the instrument exits 6: the control) all exercised; the
   scripts with `bash -n` and shellcheck; `pytest --setup-plan` of the three new
   live modules with their variables set (D671).

**Done.** *(executor: the rehearsal's transcript; the instrument's exit 6 on the
leaking fixture; the image digest used; nothing committed but this paragraph and
the two test modules + the driver — a code commit: CI read.)*

### Run 9 — the bump, the registry, the gate, the threat rows, the Ledger to `trial`

**Read first:** §2 whole; `src/agentic_postgres/__init__.py:1146-1313`;
`docs/plans/session-42-implementation-plan.md` Run 9 (`:1462-1546`) — the
bump's list to copy; `bin/upgrade.py --also` and `src/agentic_postgres/compatibility.py`
(what a new compose service under a profile and a changed image declare);
`bin/session-42-check.sh:1-200`; `tests/contract/test_session_forty_two_gate_modes.py:40-120`.

1. **The constant and the version**: `CURRENT_SESSION = 43` (`:1270`) with
   Session 43's paragraph (the D690 shape of `:1207-1269`); `VERSION` `1.21.0`;
   `README.md:7`; every `--session 42`/`--through-session 42` literal on the
   documented path moved and counted per file (D678/D1484); the operator guide
   and upgrade guide's *"This page is part of release"* lines and the upgrade
   table's row (`test_documentation_index.py:218-223, 321-380`).
2. **The registry**: §2's twenty requirements under `# Session 43 (ADR
   0280-0284)` after `:8030`, node ids read from `pytest --collect-only -q`;
   the regex gains `CON|SITE`; `CLAIMS` and `OFFLINE_CLAIMS` blocks;
   `CLAIM_INTRODUCED_IN`; `APG_CONSOLE_RECORD_FILE` in the roster.
3. **The gate**: `bin/session-43-check.sh` from 42's by `sed` of the session
   numbers into a copy, then the header and usage block rewritten whole
   (D1488), then `--console-record-file` added (D2677) — **`diff
   bin/session-42-check.sh bin/session-43-check.sh` read whole before the
   commit; every hunk named in the `**Done.**`**. `SHELL_COMMANDS` gains it after
   `:265`; `tests/contract/test_session_forty_three_gate_modes.py` from 42's by
   the same method, `SESSION_FORTY_THREE_CLAIMS` the twenty.
4. **The Ledger** (D2665): `console` → `trial` with `evidence` the Session 43
   claims that prove it (ADR 0261: only claims this session introduces);
   `sql_editor` → `planned`, `target_session: 44`, `customer_text: Not open
   yet.`; `schemas/reality-ledger.schema.json:121-128` maximum 45;
   `management_api` and `cli_remote` texts; `test_every_console_page_maps_to_a_reachable_row`'s
   exception for the `console` row removed (Run 4 step 4); `bin/render-reality-ledger.py
   --write`.
5. **The threat rows' requirements**: the five `THR-*` rows of Run 1 name their
   requirement ids now (the table's convention).
6. **The derived documents** (CLAUDE.md §5's list): `render-acceptance-matrix.py
   --write`, `render-config.py --bounds-doc --write` (the console's bounds),
   `bin/app-contract.sh --check`, `bin/mcp-contract.sh check`, `bin/apg.sh
   generate --check --project project.example.yaml`, `render-mcp-catalog.py
   --write`, `render-evaluation-report.py --write`.
7. **The gates, in shards, once** (D2554; `~/s43/run9/` from `~/s42/run9/`'s
   `gate01-*.sh` and `gate42-*.sh` by diff; `TMPDIR=~/s43/tmp`; each shard under
   `timeout 570` in the foreground; the JUnit merged; the total checked against
   the collected count): `bin/session-01-check.sh` and `bin/session-43-check.sh
   --mode offline`. Commit **after** both pass (the gate refuses a dirty tree:
   commit, gate, push — the commit is made first, the gates read it, then the
   push). Read CI. Then a documentation commit recording the gates (no CI read).

**Done.** *(executor: the counts from the tuples; the gate diff's hunks; each
shard's result and the totals; the SHA and CI.)*

### Run 10 — the sitting: the release, the dry run, the walk, the sweep, the tag, the publish

**Read first:** this plan's appendix (every sheet below) and §7; Session 42's
Run 10–11 text and rows D2634–D2649 (*what went wrong*, D977); `~/s42/run11/NOTES.md`.
**Before the first sheet**: `upgrade plan` is read (R1); the checkout on the
host moved to the Run 9 commit by bundle (`git bundle` + `scp` to
`/tmp/apg-<sha>.bundle`, `git fetch`, `git rev-parse FETCH_HEAD` confirmed,
`git checkout`), `uv sync`, the renders of the four projects (`--render-only`
as `op`), `pytest --setup-plan` of the host modules with the variables set.

1. **R1** (price) → **R2a** beta-dev, **R2b** alpha-dev, **R2c** `slot3-prod`
   by `slot.sh redeploy`, **R2d** control-prod — each with `s43-window.py`
   probing that project's routes once a second, each read by `s43-after.sh`
   before the next sheet (D1510). After R2d: `curl -sI
   https://control.agenticpostgresql.com/console/` → 200 with the CSP; `/` →
   the redirect; `/api/v1/me` → 401 (unchanged).
2. **A1** (the registry agrees ×4 + the deleted slots), **RA** (the admission
   rehearsal at the deployed commit, D2494), **K1** (the kit and the op copies
   of the four documents).
3. **V1** — the whole host suite writing nothing (`-k` none; `--dry` evidence
   off, as Session 42's V1) — and **X0** — the external suite, `-k` the Session
   43 module excluded, writing nothing. **W0** — `s43-walk.sh --dry` (stops
   before the rotation; the invitation, account, factor, session and Connect
   page exercised) — **the operator scans W0's QR with their phone** once, from
   a screenshot the driver saves to the 0700 output directory (`page.screenshot`
   of the QR element only), and confirms the phone shows `agentic-postgres` and
   a six-digit code; the screenshot is shredded after. **If V1, X0 or W0 fails:
   repair, move the commit, redeploy all four** (no slot is consumed — moving
   the commit costs a redeploy, D2671).
4. **W1** — `s43-walk.sh` (the record, the password file, the creds copy, the
   walker removed).
5. **S1** — the one sweep (`s43-sweep.sh`; host evidence with the live slot's
   outputs as Session 42's). Then **the external half** from WSL
   (`s43-external.sh` with `--console-record-file`), then **the merge**
   (`write-session-evidence` with the CI artifact's offline half for the
   deployed SHA). **Exit 5 for `documented_path` only** (§7).
6. **The tag** from the workstation (D2041): `git tag -a 1.21.0 <sha> -F
   msg.txt`, `git push origin 1.21.0`. **Read the `publish-cli` run for the
   tag** (`gh api "repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<sha>"`
   lists `contract`, `site` and `publish-cli`): `verify` green, `build` green,
   `publish` green. Then read `https://pypi.org/pypi/agentic-postgres-cli/json`
   → `info.version` `1.21.0`, and **install it** in a clean `python:3.12`
   container (`pip install agentic-postgres-cli==1.21.0 && apg --version`) —
   recorded as the close's reading (it is not in the evidence: the evidence was
   merged before the tag that publishes, §7).
7. **SL** — none (no slot). **Sheet RC1**: the reconciler started and read
   active after the last sheet that stopped it (D2178).

**Done.** *(executor: each window per project; the console's headers; V1/X0/W0
results; W1's record summary (steps, FCP ×3, link→string seconds); the merge's
counts; the tag object; the publish run's id and verdict; PyPI's version and the
clean install's output.)*

### Run 11 — the close

1. **The Ledger**: `console` → `beta` if `console_walk_live`, `console_csrf_live`,
   `console_live_host` and the offline `CON-*` claims passed in
   `evidence/session-43.json`; `cli_remote`'s `today`/`customer_text` name the
   PyPI install (its evidence `cli_package` and the reading); **no row `trial`
   at the close** (ADR 0261).
2. **The envelope**: `capacity.ENVELOPE` gains a Session 43 section after
   `:2336` — the console's memory and pids peaks (Run 4) and on the host (S1's
   reading), each project's release window (R2a–R2d), the console's FCP ×3 and
   the link→string time **named as from the operator's workstation** (D2675);
   `UNMEASURED` loses nothing it did not measure.
3. **The documents**: `docs/scope-closure.md` §36 (*What Session 43 closed, what
   it left, and what Session 44 inherits*) in §35's shape; the stage plan's
   Status block re-read and rewritten (the sessions line, `CURRENT_SESSION`, the
   evidence, the ADR and requirement counts, the next free numbers); this plan's
   Status line; `docs/operator-guide.md`'s release notes for 1.21.0 (the console,
   the cookie, the link, the site, the package; *"1.21.0 restarts no database"*).
4. **The handoff** (outside the repository): the launch folder's `CLAUDE.md` §2
   rows SESSION 43, RELEASE, EVIDENCE, CURRENT_SESSION, HOST and the new SITE /
   PACKAGE facts — copied to the scratchpad first (CLAUDE.md's own rule); the
   project memory's state file.
5. Targeted: `test_reality_ledger`, `test_evidence_claims`,
   `test_documentation_index`, the capacity envelope's test (`grep -ln
   "ENVELOPE" tests/contract`). `bin/session-01-check.sh` once (generated
   artefacts moved). Commit, push, read CI (the `site` workflow redeploys the
   Ledger page — its verdict read too).

**Done.** *(executor.)*

---

## 7. Evidence and claims

**Expected at the merge** (Run 10): **322 claims** (149 offline). **`failed` 1:
`documented_path`** (D1935). Everything else **passed**, Session 42's external
proofs included — they re-run against the Session 42 lifecycle record, which is
unchanged (no slot moved), and Session 41–42's branch proofs read the `deleted`
phase as before (D2647's order holds: sweep, then external). **Exit 5 for
`documented_path` and no other reason.** Predictions, each moved only by the
evidence.

**The three modes.** Offline: CI's artifact for the deployed SHA (149 claims).
Host: S1 with the same flags as Session 42's (`--lifecycle-record-file` the
Session 42 record, `--live-slot-outputs` `slot3-prod`). External: from WSL
with `--control-outputs`, `--control-probe-file`, `--lifecycle-record-file`,
`--customer-credential-dir` (**the creds directory W1 updated** — so the
Session 39 customer proofs read the rotated `customer_app` password, and must:
**if a Session 39–42 external proof reads the `customer_app` password from a
copy made before W1, it fails; Run 8 greps every reader of
`--customer-credential-dir`/`APG_CUSTOMER_CREDENTIAL_DIR` and records which file
each reads**), and `--console-record-file`. **The Session 43 customer proofs
reach only `routes.control`, the console's origin, the site's two names and the
public names on 5432, and open no SSH.** **Deploy every project fully, THEN the
dry run (V1, X0, W0), THEN W1, THEN sweep, THEN external — every half at one
commit; THEN the tag; THEN the publish.**

**What is not in the evidence, by construction**: the PyPI install (the tag
publishes after the merge) and the site's Pages deployment of the tagged
commit (the `site` workflow runs on the push to `main`, before the tag — the
external `site_live` proof reads the site the deployed commit's push produced,
by its build digest). Both are recorded in Run 10's `**Done.**` and the
envelope.

---

## 8. Security invariants this session touches

| Invariant | How this session keeps it |
|---|---|
| **A product surface runs no SQL** | The console calls named `/v1` routes; no script holds a statement (`test_no_script_holds_sql`); no data view (D2661) |
| **The control plane holds nothing that opens a project's data or admin plane** | The browser computes the SCRAM verifier and sends only it; the password is shown once by the page and never crosses `/v1` (D2660) |
| **A credential shown to a customer is shown once and stored hashed or materialised, never logged** | Passwords, keys, invitation links and export links rendered once, dropped on leaving the view, never in storage or a URL; the invitation in the fragment (D2657); the cookie and token canaries (D2678) |
| **No script on the page can read the session** (D2595) | `__Host-`, `HttpOnly`, `Secure`, `SameSite=Strict` (D2656); rig 43a's (5) |
| **A forged cross-site request is refused** | Strict + `X-Apg-Console` + `Origin` on writes; no CORS (D2656; rig 43a's (2)–(4)) |
| **No third-party script in the console, no tracker on the site** (D2596) | Every asset our own file (two guards); the CSPs `default-src 'none'`; the site's build scan |
| **Nothing `planned` has a control** | Every console page and every site page maps to a reachable row; the build and the guard refuse otherwise |
| **No surface claims more than the node does** (Stage 5's failure mode) | Pricing from `PLANS`, the Ledger page from the YAML, `customer_text` corrected (D2664, D2665, D2674) |
| **No published port beyond ADR 0246's list; DNS records naming the host stay DNS-only** | The console is a route on the existing 443; the site is Cloudflare's (D2651); C4 reads every host record still DNS-only |
| **Never a GitHub credential on the VPS; no secret in the tree** | The Pages token only in a GitHub environment; PyPI by OIDC, no token at all (D2653, D2667) |
| **A report may not substitute an answer for a failure to determine one** | Insights' `could_not_determine` shown as such; `telemetry.sh status` reads the gateway (D2636); a walk step that could not be read is recorded `unread`, never `ok` |

---

## 9. Stop conditions

Stop and ask the operator, without improvising, when:

- **Sheet C0** finds anything on the zone but p5/p6's one route and one AAAA
  record, or the route's script is not `forgeai-sandbox`;
- **rig 43a**: a cross-origin `fetch` with the custom header reaches the
  handler, or a cross-site POST or navigation carries a `Strict` cookie, or
  Chromium's PBKDF2 differs from Python's;
- **rig 43b**: the decoded QR differs from the URI, or `segno` has a dependency
  or a licence other than a permissive one;
- **rig 43c**: Pages does not apply `_headers` to the HTML pages, or adds a
  script or a third-party request of its own;
- **the repository has no licence file** when Run 6 stages the package (a
  public distribution needs the operator's licence decision);
- **PyPI says `agentic-postgres-cli` is taken** at any read, or the pending
  publisher cannot be registered;
- a design here would need the console to proxy `/api`, hold a token in page
  memory or storage, run SQL, show a `planned` feature, load a third-party
  file, or the control plane to see a database password;
- a cookie would need `SameSite=Lax` or a CORS header to work;
- `upgrade plan` prices 1.21.0 at `major`, or for a reason this plan did not
  name;
- a deploy's window on any project exceeds 5 minutes, or a project's routes do
  not return after its R2 sheet, or **the console's router answers any path
  outside `/`, `/accept`, `/console/…`**;
- **W1's connection with the shown password fails** after the rotation reported
  success (the customer's door and the page disagree: the reconciler's userlist
  sync is read before anything is retried; `customer_app` is the kept project's
  credential);
- the `publish-cli` run publishes from anything but the tag, or its `verify`
  passes on a SHA without a green `contract` run;
- a `trial` row would outlive the close, or a row would move to `beta` without
  its claims `passed`;
- a currently-passing test would be weakened to make a new one pass;
- `--render-only` stops working with no host and no root.

---

## 10. Open items this session carries and creates

**Carried, untouched, each still true:** everything in Session 42's §10 *Carried*
list (`docs/plans/session-42-implementation-plan.md:1792-1812`) — M7's X1/X2
(Hetzner) and the store's 443 rule for it (D2640); beta's three rotations
(D1995); D1936/D2005; D1547; D1642, D1798, D1869, D1871, D1722/D1806, D1784,
D1792, ADR 0241's bound; D1045; D1375; D976; D688; D771; D340; D466; D540; D942;
D1203; D1205; D1211; the 24 unclaimed requirements; `process-max` 1 (D593);
`documented_path` (D1935); accounts and organisations never deleted (D2065,
D1986); TOTP seeds plaintext (ADR 0252); `/v1/sessions` unthrottled (D2166,
D2679 — **now linked from a public page**); the reconciler and the operator
serialised by a rule (D2178); a slot's provider resources outlive it (D2181);
the telemetry plane's volumes not backed up; the plane's footprint at rest and a
usage pass's duration `UNMEASURED`; `slot1-` … `slot6-prod` consumed;
`lifecycle-s41`, `lifecycle-s42` empty.

**Created, and named so Session 44 does not inherit them silently:**

- **The console is a second public surface on the control host**: its outage is
  a route's 502 while `/api/v1` keeps answering (separate containers); its
  footprint is charged nowhere (ceilings only, like every non-database service).
- **The session cookie lives 30 days on the refresh side**; signing out of one
  browser ends that family only. A *"sign out everywhere"* is the existing
  factor-confirm behaviour, not a button.
- **The site is deployed on every green push to `main`**, so it can be ahead
  of the deployed release (a page describing a console change not yet
  deployed). The Ledger guard keeps it honest about *rows*, not about *which
  commit the host runs*; the site's footer names `VERSION`. A per-release
  deploy is the operator's to ask for.
- **A PyPI version cannot be re-uploaded**: a broken `1.21.0` is fixed by
  `1.21.1`, which needs a tag — a release, under D1425's one-commit rule. A
  CLI-only fix therefore costs a release of four; recorded, not solved.
- **The walker account `walk-s43-…` remains**, its membership removed; the
  `customer_app` password of `slot3-prod` is the one W1 set.
- **Email Routing forwards to the operator's inbox**: messages to `invite@`
  are personal data the product never stores; the operator's inbox holds them.
- **Session 44 starts from here**: the editor page joins the console under the
  same CSP (it will need `connect-src` to its relay's `wss:` origin — that
  session's ADR amends 0280's constant), the same session cookie, and the
  `sql_editor` row at `planned` → 44.
- **Session 45's walk** needs `slot7-prod` prepared and an ACCOUNT invitation
  (D2669); the walker reads only the site.

---

## Appendix — what to consult, how a run is executed here, and the sheets

**Consult, in this order:** CLAUDE.md §1 (the shell traps); this plan's §0, §1
and the run's own text; the reads its run names. **The tree wins.**

**How a run is executed here**: CLAUDE.md §5. Every `sudo` line is the
operator's, on a sheet, under `script -q -e -c '…' /home/op/s43-<sheet>.txt`
when it execs into a container or deploys (D972, D1501), never piped or
redirected; `sudo -v` in the foreground first (D1376). Every `op` line is the
agent's over SSH; remote loops in a script file with
`PATH="$HOME/.local/bin:$PATH"` exported. **`<sha>` is never typed on a sheet**:
the agent fills it from `git rev-parse HEAD` on the host before handing the
sheet. **Before any sheet that deploys: `sudo systemctl stop
agentic-postgres-reconciler`, and `start` after** (D2178); **after any checkout
move: restart it** (D2411, D2179). **Read `--help` of every command on a sheet
before handing it** and correct the line to it. **A sheet may not hand over a
command whose precondition is the previous sheet's success** (D1510): one
sheet, one outcome, read before the next. **No secret value is ever typed into
the conversation**: tokens and passwords go into 0600 files by `nano` or into a
provider's own form.

### Sheet C0 — the zone's wildcard (Run 1; the agent, the operator's decision D2650)

```
(agent, Cloudflare API)  GET  /zones?name=agenticpostgresql.com             -> zone id
                         GET  /zones/{zone}/workers/routes                  -> exactly one: *.agenticpostgresql.com/* -> forgeai-sandbox
                         GET  /zones/{zone}/dns_records?type=AAAA           -> exactly one: * -> 100:: proxied
                         DELETE /zones/{zone}/workers/routes/{route_id}
                         DELETE /zones/{zone}/dns_records/{record_id}
                         GET  both lists again                              -> empty
                         GET  /zones/{zone}/dns_records?per_page=100        -> 23 records, every A proxied:false
(agent, workstation)     nslookup www.agenticpostgresql.com 1.1.1.1          -> no address
```

### Sheet C1 — the invitation address (Run 1; the operator, Cloudflare dashboard)

```
1. dash.cloudflare.com -> agenticpostgresql.com -> Email -> Email Routing -> Enable
   (accept the MX and TXT records it proposes; it adds them DNS-only).
2. Destination addresses -> add your inbox -> click the verification mail.
3. Routing rules -> Custom address: invite@agenticpostgresql.com -> Send to: your inbox -> Save.
4. From another mail account, send a test to invite@agenticpostgresql.com; tell the agent it arrived.
(agent) reads the MX/TXT records through the API: present, proxied:false; nothing else changed.
```

### Sheet C2 — the PyPI pending publisher (Run 1; the operator, pypi.org)

```
1. Sign in to pypi.org (two-factor on).  Your account -> Publishing -> "Add a new pending publisher" -> GitHub.
2. PyPI Project Name: agentic-postgres-cli
   Owner: Virabyan99      Repository name: agentic-postgres
   Workflow name: publish-cli.yml      Environment name: pypi
3. Add.  Tell the agent the five values as the page shows them (no screenshot needed).
```

### Sheet C3 — the Pages token and the two GitHub environments (Run 1; the operator)

```
1. dash.cloudflare.com -> My Profile -> API Tokens -> Create Token -> Custom:
   Permissions: Account / Cloudflare Pages / Edit.   Account Resources: Include / <this account>.
   TTL: none (or a date you will renew).  Create.  Copy it ONCE.
2. github.com/Virabyan99/agentic-postgres -> Settings -> Environments -> New environment "site":
   Deployment branches: Selected -> main.   Add secret CLOUDFLARE_API_TOKEN = <the token>.
   Add variable CLOUDFLARE_ACCOUNT_ID = <the account id the agent gives you>.
3. New environment "pypi": Deployment branches and tags: Selected -> tag pattern [0-9]*.[0-9]*.[0-9]*.
   No secret.  (Optional: Required reviewers -> you.)
(agent, Git Bash) gh api repos/Virabyan99/agentic-postgres/environments --jq '.environments[].name'
                  -> includes site and pypi
```

**For rig 43c only**, a second, temporary token with the same permission, put by
the operator into WSL `~/s43/rigs/pages-token` by `nano` + `chmod 0600`, and
revoked in the dashboard when the rig ends (the agent reads 401 with it).

### Sheet C4 — the site's custom domains (Run 7; the agent)

```
(agent) POST /accounts/{acct}/pages/projects/agentic-postgres-site/domains  {"name":"agenticpostgresql.com"}
        POST ...                                                         {"name":"www.agenticpostgresql.com"}
        GET  .../domains  every 60 s up to 30 min                         -> both status active (never re-POST on a failure)
        GET  /zones/{zone}/dns_records                                   -> the two Pages records proxied:true; every A proxied:false
        curl -sI https://agenticpostgresql.com/ https://www.agenticpostgresql.com/   -> 200, the CSP
```

### Sheet R1 — the release priced (Run 10)

```
sudo -v
cd ~/agentic-postgres && sudo bin/upgrade.sh plan --project-file /home/op/<each>.yaml   # the verb and flags read
                                                                                          # from --help by the agent;
                                                                                          # 'minor', for the reasons §0 names
```

### Sheets R2a / R2b / R2c / R2d — 1.21.0 deployed (Run 10; one per sheet, read before the next)

```
sudo systemctl stop agentic-postgres-reconciler
script -q -e -c 'sudo ./deploy.sh <the project manifest as Session 42 R2a-c used it>' /home/op/s43-r2<x>.txt
   # R2c: slot3-prod by slot.sh redeploy (refused while the reconciler is active)
   # R2d: control-prod LAST -- the console starts with it
(agent) s43-after.sh <key>: doctor 12 ok; the routes; for R2d the console container, /console/ 200 + CSP
sudo systemctl start agentic-postgres-reconciler          # after R2d only
```

### Sheets A1, RA, K1, V1 (Run 10) — as Session 42's (`session-42-implementation-plan.md` Sheets A1, RA, K1, V1), the commit and file names moved to 43; RA after the last deploy (D2494).

### Sheet W0 / W1 — the walk (Run 10; the agent, from WSL, no SSH)

```
(agent) ~/s43/run8/s43-walk.sh --dry      # W0: invitation link minted by the probe owner, the driver to the Connect page,
                                          #     the QR screenshot for the operator's phone, the walker removed
(operator) scan the QR from the 0700 directory's screenshot; read "agentic-postgres" and a code; the agent shreds it
(agent) ~/s43/run8/s43-walk.sh            # W1: the whole walk, the rotation, the creds copy, the walker removed
```

### Sheet S1 — the one sweep (Run 10)

```
sudo -v
script -q -e -c 'sudo bash /home/op/s43-sweep.sh' /home/op/s43-s1.txt
   # derived from ~/s42/run8/s42-sweep.sh by diff; the plane read from docker ps (D2646); the evidence file named by the agent
```
