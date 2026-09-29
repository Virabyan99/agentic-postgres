# 0238 — Outbound delivery is the worker's second pass: signed, at-least-once, fixed backoff, dead-lettered, never redirected, and it records no URL, payload or key

- **Status:** Accepted
- **Date:** 2026-09-29
- **Session:** 34, Run 1 (D1786, D1790, D1791, D1792, D1794, D1800, D1801,
  D1802, D1803, D1809, D1812, D1813; rigs 34b, 34d)
- **Affects:** migration 0036 (`connector_delivery`,
  `connector_claim_delivery`, `connector_finish_delivery`,
  `connector_rehearse_delivery`, the replaced `workflow_counts`),
  `services/auth-api/app/connector_delivery.py`,
  `services/auth-api/app/workflow_worker.py` (`run_forever`),
  `tests/contract/test_auth_service_shape.py` (one allowlist row),
  `bin/doctor.py`, `src/agentic_postgres/diagnosis.py`,
  `src/agentic_postgres/rehearsal.py`, `bin/restore-test.py`.
- **Related:** ADR 0226 (one loop in the auth process), ADR 0213 (a reading
  with no threshold), ADR 0190/0193 (rehearsals), ADR 0195 (three outcomes),
  ADR 0235 (the event), ADR 0237 (the scheme).

## Context

The loop has one task and one kind of work, and a proof asserts exactly one
`create_task` in `main.py`. The worker's transport row says it reaches exactly
one address built from three constants; a delivery to an operator's URL would
make that sentence false. The auth container sits on `internal` (no egress) and
`edge`.

**Rig 34b measured the transport** inside the auth image:

- **Redirects** (D1812). For a POST, the DEFAULT opener follows 301, 302 and
  303 as a **GET with no body that still carries `X-Apg-Signature`** to the
  `Location`, and reports the Location's 200 as the response; it refuses 307
  and 308 with `HTTPError`. It never re-POSTs the body. An opener whose
  `redirect_request` returns `None` surfaces all five as `HTTPError(<code>)`.
- **Failures** (D1813), each with a real target: connection refused
  (`127.0.0.1:9`) → `URLError` whose `.reason` is `ConnectionRefusedError`
  (errno 111); a connect timeout (`10.255.255.1`) → `URLError` whose `.reason`
  is `TimeoutError`; a name that does not resolve → `URLError` whose `.reason`
  is `socket.gaierror` (errno −2; −5 on a network with no resolver for it); a
  self-signed certificate → `URLError` whose `.reason` is
  `ssl.SSLCertVerificationError` (a subclass of `ssl.SSLError`). **A READ
  timeout — a server that accepts and never answers — raises a bare
  `TimeoutError`, not a `URLError`.**

**Rig 34d measured the trip's sink**: a container started from the auth image
on an `internal: true` network with alias `apg-s34-sink` answered `/ok` 200 and
`/fail` 500 to a client attached to that network and a second one, and printed
the three `X-Apg-*` headers exactly as sent. Control: a client on the second
network alone could not resolve the alias (`gaierror`).

## Decision

1. **Delivery and the schedule are PASSES inside `run_forever`**, never a
   second task: each iteration heartbeats, claims and processes at most ONE
   step, claims and delivers at most ONE due delivery, and fires due schedules
   once; it sleeps `POLL_SECONDS` only when the iteration did nothing.
2. **A new module `services/auth-api/app/connector_delivery.py`** owns the one
   outbound POST, with its own transport-allowlist row (`urllib`; *"delivers
   one signed body to the endpoint an operator declared for one connector;
   follows no redirect; `socket` is not granted"*) and joins `senders`. The
   opener refuses every redirect; a 3xx is the attempt's result. The loop's own
   row and sentence stay exactly as they are.
3. **Body and headers**: the canonical JSON of `{id, name, version,
   occurred_at, payload}`, the three `X-Apg-*` headers, the signature of ADR
   0237 under the connector's derived key. No bearer, no cookie, no project
   credential.
4. **Retry**: `retry: {max: 0..10, backoff_seconds: 1..3600}`, fixed backoff;
   attempts = `max + 1`; every non-2xx and every transport failure is retried
   until then, then `dead`. `DELIVERY_TIMEOUT_SECONDS = 10`; the lease is `10 +
   lease_margin_seconds()`; a lost lease re-delivers (at-least-once).
5. **Error tokens, fixed, never a message**: `http_<code>` for an
   `HTTPError`; otherwise the classifier reads the `URLError`'s `.reason` when
   there is one and the exception itself when there is not, in this order —
   `ssl.SSLError` → `tls_failed`, `TimeoutError` → `timeout`,
   `socket.gaierror` → `dns_failed`, `ConnectionError` → `connect_failed`,
   anything else → `unknown`.
6. **The URL appears in no document, record, status, log line or error.** The
   worker reads it from the connector row for one attempt.
7. **Compensation is not reused** (D1794): a dead delivery changed nothing in
   the database, so there is nothing to undo; it is terminal and visible.
8. **Readers**: still twelve doctor checks — `workflow_counts` gains
   `deliveries_pending`, `deliveries_dead`,
   `oldest_pending_delivery_age_seconds`, `connectors_enabled`, and the line
   says *not read* rather than zero when the substrate predates 1.12.0; the
   drill's `workflow_runs` member nests `deliveries` by status; the eleventh
   rehearsal `delivery-retry-storm` induces one delivery through a function
   granted to nobody, sent to `http://127.0.0.1:9/`, and observes three
   attempts, a dead letter `connect_failed` and a moving heartbeat.

## Consequences

- A failing endpoint costs `max + 1` attempts and a dead letter, never a hot
  loop, and cannot starve steps.
- A receiver MUST de-duplicate on `X-Apg-Delivery`.
- An endpoint naming an internal service would receive the signed body and
  nothing else; the operator declares it in a root-owned manifest, and
  `THR-DELIVERY` says so.

## Alternatives rejected

- **A second asyncio task** — ADR 0226's reason, and the one-task proof.
- **Exponential backoff** — the brief says *declared*.
- **Treating a 4xx as terminal** — a receiver fixed later often accepts; the
  retries are bounded anyway.
- **The default opener** — it would record a 301/302/303 as *delivered* after
  sending the signature header to an address nobody declared (rig 34b).
- **Reusing compensation** — no subject.
