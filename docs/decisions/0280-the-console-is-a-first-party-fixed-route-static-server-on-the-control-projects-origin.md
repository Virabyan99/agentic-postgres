# 0280 — The console is a first-party fixed-route static server on the control project's origin

- **Status:** Accepted; decision 4's policy constant and decision 6 amended by ADR 0285 (Session 44)
- **Date:** 2026-10-19
- **Session:** 43, Run 1 (`docs/plans/session-43-implementation-plan.md`,
  D2655, D2660, D2661, D2668, D2675, D2680, D2686; rigs 43a, 43e)
- **Affects:** `services/console/` (new image: `Dockerfile`, `serve.py`, the
  pages, `scram.js`), `compose.yaml` (service `console`, profile `console`),
  `bin/project-runtime.sh` (adds the profile when the render says
  `APG_CONSOLE=1`), `src/agentic_postgres/rendering.py` and `naming.py` (the
  console's router and origin, the control project only),
  `docs/reality-ledger.yaml` (`console`), `tests/contract/test_reality_ledger.py`
  (`test_no_console_exists_yet` replaced), `tests/external/browser/console_walk.py`.
  Requirements `CON-SERVE-001`, `CON-PLANE-001`, `CON-LEDGER-001`,
  `CON-SCRAM-001`, `CON-HOST-001`, `CON-LIVE-001`.
- **Amends:** the Reality Ledger guard `LEDGER-001`: `test_no_console_exists_yet`
  is replaced by `test_every_console_page_maps_to_a_reachable_row` (the old
  test's own docstring names this replacement).
- **Related:** ADR 0069 (the docs container's own CSP), ADR 0155 (a deploy
  recreates what changed), ADR 0205 (Studio, loopback only), ADR 0244 (every
  service bounded), ADR 0246 (the hosted boundary), ADR 0254 (the Ledger's
  operation gate), ADR 0281 (the session), ADR 0282 (the invitation link and
  the QR), D2344 (a facility profile), D2592 (the SQL editor is Session 44's).

## Context

The stage plan asks for a console of static files that calls `/api/v1` only,
served from `control.agenticpostgresql.com` (D2591, D2595). Nothing answers
`/` on the control host today: every router rule is a specific path, so `/` is
Traefik's own 404. `auth-api` serves no static file and sets no
Content-Security-Policy in control mode. Two first-party precedents exist. The
docs container (`services/docs/serve.py`) is a fixed route table with its own
CSP, GET and HEAD only, and a log line that names no query. The facility
profile (`public-endpoints`) starts a service on one project only. Studio
(ADR 0205) is a loopback process that holds a member's project token, and it
is never published.

## Measured

- Rig 43a (ADR 0281): Chromium's WebCrypto PBKDF2-HMAC-SHA-256 at 4,096
  iterations equals Python's `hashlib.pbkdf2_hmac` byte-for-byte (the control,
  4,095, differs). The verifier the console computes can therefore equal
  `agentic_postgres.scram.verifier` for the same password and salt.
- Rig 43e (2026-10-19, `~/s43/rigs/43e.txt`):
  `mcr.microsoft.com/playwright/python:v1.63.0-noble` (Playwright 1.63.0,
  2026-09-15, the newest release at least 14 days old), index digest
  `sha256:72bd171a9ffc2b4b59532aaa6210e21014d07093120dc25528870c0b840da1f0`,
  1,013,940,272 bytes. It holds Python 3.12.3 and the browsers
  (`chromium-1243`, `firefox-1543`, `webkit-2359`) under
  `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`, **but not the `playwright`
  package** (`import playwright` → `ModuleNotFoundError`; D2686). Installed
  with `pip install --target` (`playwright==1.63.0`, `greenlet` 3.5.6, `pyee`
  13.0.1, `typing_extensions` 4.16.0; the image has no `ensurepip`, so a venv
  fails), Chromium **153.0.8010.12** launches headless. A page's
  `performance.getEntriesByType('paint')` holds `first-contentful-paint`
  (124 ms for a two-element page). The control, `about:blank`, holds none.

## Decision

1. **A new image, `services/console/`**, built from `PYTHON_BASE_IMAGE` (the
   compose build argument that `versions.env`'s `PYTHON_RUNTIME_IMAGE` fills,
   D2680) alone. Its `serve.py` takes the shape of `services/docs/serve.py`: a
   fixed route table, no path joining, GET and HEAD only, `log_message`
   naming the path without its query. It runs as uid 65532 with a healthcheck
   through `urllib`. **It never authenticates, never proxies `/api`, and holds
   nothing.**
2. **A compose service `console` under the facility profile `console`.**
   `bin/project-runtime.sh` adds `--profile console` only when the render says
   `APG_CONSOLE=1`, which `rendering.py` emits beside `AUTH_APP_MODE=control`,
   so only the control project runs it. The deploy builds its router from the
   same value (`_override_console`), so the container and its router cannot
   disagree. The service is bounded by ADR 0244's rule from its measured peaks
   (Session 43 Run 4, `~/s43/run4/measure.txt`: 1,008 requests over every
   route, `memory.peak` 44.07 MiB, `pids.peak` 8): **`mem_limit` 192 MiB,
   `pids_limit` 64, `cpus` 0.25** (a quarter of a core, less than any
   sidecar's 1.0), from `CONSOLE_*` variables, `read_only: true`, uid 65532,
   on network `edge` only, with no secret and no mount. Its environment is the
   port and **`APG_CONSOLE_API_PATH`** — the rendered `CONTROL_ROUTE_PATH` —
   which the server answers at `/console/env.json`, so no page types a path
   `naming` derives (D2697).
3. **One router, `apg-<key>-console`** (derived in `naming.py`), with the rule
   ``Host(PROJECT_DOMAIN) && (Path(`/`) || Path(`/accept`) ||
   PathPrefix(`/console/`))`` and the baseline middleware chain. `/api/…`,
   `/docs/…` and `/__apg/…` keep their own routers.
4. **The Content-Security-Policy, one constant, on every answer** (404 and
   redirects included):

   ```
   default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:;
   connect-src 'self'; font-src 'none'; base-uri 'none'; form-action 'none';
   frame-ancestors 'none'
   ```

   It has **no `'unsafe-inline'` anywhere**, because the console's CSS and
   scripts are its own files. `img-src data:` exists only for ADR 0282's QR.
   The other headers are `services/docs/serve.py`'s: `Referrer-Policy:
   no-referrer`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
   COOP and CORP `same-origin`, `Cache-Control: no-store`. They are added in
   `end_headers`, so the base handler's own 501 for another verb carries them
   too (the docs server's 501 does not, D2700).
5. **Every page maps to a Ledger row that is `trial`, `beta` or
   `available`, and every `/v1` path a script calls exists in
   `contracts/control-openapi.canonical.json`.** No page names a `planned` or
   `not_offered` row. No script builds SQL, writes `localStorage` or
   `sessionStorage`, or holds a token (ADR 0281). This guard replaces
   `test_no_console_exists_yet`.
6. **No project data view** (D2661). A customer reaches their data with their
   own client, through the Connect page's strings, and from Session 44 through
   the SQL editor (D2592). Studio stays loopback-only (ADR 0205).
7. **The browser never sends a database password** (D2660). `scram.js` draws
   32 random bytes (`crypto.getRandomValues`, base64url — the CLI's
   `secrets.token_urlsafe(32)`, D2698) as the password,
   computes the SCRAM-SHA-256 verifier with WebCrypto (rig 43a, reading 6),
   sends only the verifier, and shows the password once. It is held in a
   closure until the page is left, and never written to storage or a URL. A
   contract test runs `scram.js` under Node's WebCrypto and compares it to
   `scram.verifier(password, salt=…)`.
8. **The browser walk is Playwright in its pinned image** (D2668): the image
   above by digest, with the package installed into a target directory from a
   hash-locked requirement (D2686). `tests/external/browser/console_walk.py`
   drives the console and writes one record (0600, no secret value), which the
   external proofs read through `APG_CONSOLE_RECORD_FILE`. The driver records
   `first-contentful-paint` and `domContentLoadedEventEnd` for `/console/`
   three times, cold, and the time from link to connection string. Those
   numbers are named as **from the operator's workstation over its own
   network** (D2675).

## Alternatives

- **Static files served by `auth-api`** (`StaticFiles` in control mode): it
  puts HTML into the process that verifies sessions, and the CSP would be a
  middleware on an API. Rejected.
- **A console on Cloudflare Pages beside the site**: a different origin from
  `/api/v1`, so either CORS with credentials or a proxy. Both are what ADR 0281
  avoids. Rejected.
- **A hosted Studio for data views**: a second server holding a member's
  project token, the boundary ADR 0205 decided against. Rejected; the editor
  is designed in Session 44.
- **Selenium or the operator's own browser for the walk**: a second driver to
  pin, or a measurement nobody can repeat. Rejected.

## Consequences

- The control host gains a second public surface. The console's outage is a
  502 on its router while `/api/v1` keeps answering (separate containers).
  Its footprint is charged at its ceilings, like any non-database service.
- Session 44's editor joins the console under this policy and will need
  `connect-src` for its relay's `wss:` origin. That session's ADR amends this
  constant.
- A page whose Ledger row is not reachable cannot ship. The Ledger decides
  what the console shows, not the other way round.
