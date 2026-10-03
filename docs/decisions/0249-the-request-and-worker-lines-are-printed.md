# 0249 — The request and worker lines are printed

- **Status:** Accepted
- **Date:** 2026-10-03
- **Session:** 36, Run 1 (D1918, D1977, D2003; rig 36c)
- **Affects:** `OPS-LOG-001`, `OPS-LOG-002` (registered by Run 8). A new
  `services/auth-api/app/log_setup.py`, called first in `create_app`
  (`services/auth-api/app/main.py`); `tests/contract/test_request_log.py` and
  `tests/deployment/test_session36_operations.py` (Run 4).
- **Related:** ADR 0019 (Traefik drops `RequestPath`), ADR 0160 (the plane's
  request id), D1837 (the worker's INFO line recorded as invisible), D1918 (no
  handler on `apg.*`), `infra/host/daemon.json` (the `local` log driver,
  `max-size` 10m, `max-file` 5).

## Context

The auth image serves three modes — `auth`, `storage`, `mcp` — from one factory,
`create_app`. Its middleware writes one line per HTTP request on the logger
`apg.http` (`main.py:391`, `:412-427`): `apg.http.request` and a JSON object of
exactly five fields — the plane's own request id, the method, the route
**template** (never the path), the status and the elapsed milliseconds. The
agent plane writes `apg.mcp.read` from a fixed field set
(`mcp_telemetry.py:58-67`); the worker writes on `app.workflow_worker`. The lines
were designed to be safe to print, and the canaries already guard their content
(`test_mcp_budgets.py`'s `caplog` and AST scans, `STO-URL-001`'s
`docker logs` scan).

**None of them is printed.** No `basicConfig`, `dictConfig`, `setLevel` or
`addHandler` exists under `services/auth-api/app/`, and the image runs
`python -u -m uvicorn --factory app.main:create_app … --no-access-log`
(`Dockerfile:118-121`), so an INFO record reaches only Python's last-resort
handler, which prints WARNING and above (D1918; D1837 for the worker). An
operator reading `apg-diag logs <project> auth` sees uvicorn's lines and none of
the product's.

### Rig 36c (Run 1)

The image's own entrypoint, from two copies of the checkout's `app/`, with
`APP_MODE=auth` and `--lifespan off` (no database; the middleware runs on
`/health/live` regardless). Five requests each: four `GET /health/live` — three
of them carrying a planted bearer token, a planted query string and a caller
`X-Request-Id` — and one `POST` with a planted body to an unmatched path.

- **Control — the tree as it is:** 0 `apg.http.request` lines on the child's
  stdout and stderr; uvicorn's four lifecycle lines only.
- **Arm — `configure_logging()` first in `create_app`:** exactly 5 lines, one
  per request; the route template (`/health/live`, and `<unmatched>` for the
  404); none of the planted token, query, body or path.
- **The caller's `X-Request-Id` appears in no line.** The plane mints its own id
  and never reads an inbound one (`request_id.py:1-5`); it is returned to the
  caller on the response's `X-Request-Id`. A live proof must therefore read the
  id from the response, never send one and look for it (D2007).

## Decision

**One stdout handler, installed once, on the loggers `apg` and
`app.workflow_worker`, at INFO**, by `log_setup.configure_logging()`, the first
statement of `create_app` — before the mode is resolved, so `auth`, `storage`
and `mcp` all get it:

- a `logging.StreamHandler(sys.stdout)` with the formatter `%(message)s` (the
  lines already begin with their own name);
- **idempotent**: the handler carries a marker attribute, and a logger that
  already holds a marked handler gains none — `create_app` called twice installs
  one;
- **propagation is left ON** (D2017, corrected in Run 4 before anything
  shipped): nothing in the image puts a handler on the root logger — rig 36c,
  re-run from Run 3's commit with propagation on, printed exactly one line per
  request (5 for 5) through the image's uvicorn argv — and the Run 1 draft's
  `propagate = False` would have blinded every `caplog` canary that reads these
  loggers (`test_mcp_budgets.py`, `test_mcp_tools.py`,
  `test_connector_delivery.py`) as soon as any test in the process had built an
  application. A doubled line needs a ROOT handler, and the proof asserts
  `create_app` adds none;
- nothing else: no field is added to any line, no other logger is configured,
  uvicorn's own logging is untouched.

**The log-volume answer** (the operator's question, D2003). Docker's `local`
driver keeps 10 MB × 5 files per container (`daemon.json`), **50 MB**. A rig
36c line is ~140 bytes of text; at ~200 bytes stored per line (the driver's
framing, uncompressed), 50 MB holds **~250,000 requests** per container before
the oldest rotates away. The auth container serves `/api/app/*` only —
PostgREST traffic never passes through it — and Session 35's measured idle and
light traffic is single requests per second, so the window is **days**. At a
sustained 480 requests per second (Session 35's saturation rate, measured
against the REST path, not this container) it would be **about nine minutes**.
The lines are the request log, not an audit: the agent audit and the workflow
record are the durable records, and the log is what an operator reads while a
problem is happening.

## Alternatives rejected

**`logging.basicConfig(level=INFO)`.** Rejected: it configures the root logger,
which every library under the process writes to, and it would print what this
repository never reviewed.

**uvicorn's `--log-config`.** Rejected: it lives in the Dockerfile's argv,
which no test of the factory reads, and the factory is what `tests/contract/`
builds. A handler installed by the code the tests construct is a handler the
tests see.

**Keep the lines silent and read the audit.** Rejected: the audit records agent
calls, not requests, and D1918's whole finding is that an operator diagnosing
a refused browser request has nothing to read.

## Consequences

**Makes easy:** `apg-diag logs <project> auth` shows one line per request with
the id a caller was handed, so a support conversation can name a request; the
worker's INFO lines (approvals withdrawn, runs claimed) become visible; Session
41's logs pipeline has a source.

**Makes hard:** a busy container's log rotates within minutes at saturation.
That is stated, not fixed: retention of request lines is Session 41's
ClickStack question.

**Enforced by:** `tests/contract/test_request_log.py` (one handler per logger,
twice-called still one, one line per request carrying the template and no
caller value, no line printed twice) and
`tests/deployment/test_session36_operations.py::test_a_request_line_reaches_the_auth_containers_log`
(the live half); the existing canaries unchanged.
