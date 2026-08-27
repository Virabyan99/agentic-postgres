# 0160 — The request id flows outward, and no caller value is ever trusted

- **Status:** accepted
- **Date:** 2026-08-27
- **Session:** 11, Run 5 (`OPS-LOG-001`)
- **Related:** **D478** (the request id stops short of ingress), **D141**
  (Session 5 deferred exactly this measurement), **D633** (a caller-supplied
  header can roll back a write), **D498** (the id's uniqueness was never
  proved), ADR 0141 (one id per HTTP request, minted before anything is
  dialled), ADR 0135 (an agent can add noise to its own audit record).

## Context

`OPS-LOG-001` asks that *one request ID propagates across ingress, API, agent,
and audit records.* Session 9 built three of the four legs: the MCP runtime mints
a uuid4 per HTTP request, forwards it upstream on every call, logs it, and writes
it to the `agent_plane` audit row. D478 recorded the missing leg — the id stops
short of ingress — and left it to this session.

**The obvious repair is wrong, and the code already says so.** The plan for this
run proposed honouring an inbound `X-Request-Id` and minting only when none was
offered. `mcp_authorization._Held`'s docstring had already refused that, with a
reason:

> It is this process's own mint and never a caller value — nothing reads a
> request id off an inbound header, because **an id a caller chose would let two
> agents' records collide on purpose.**

That reason is sound and it is sharper than it first looks. `request_id` is not a
key — the audit row's key is its own `gen_random_uuid()` — so a collision
corrupts nothing. What it does is let one agent **stamp its actions with another
agent's request id**, so an operator reading the audit trail by request sees a
second agent's writes inside a first agent's request. That is audit-trail
poisoning, by a caller, into the one record this deployment keeps to answer *who
did that*. ADR 0135 already concedes an agent can add *noise* to its own record;
letting it add noise to somebody else's is a different thing.

D633, one run earlier, is the same family measured: a caller-supplied
`X-Request-Id` reaching an unguarded cast **rolled back the caller's own write**.
Caller-controlled values in this field have now produced two distinct defects in
two runs.

## Decision

**The id flows outward, not inward.** Nothing reads a request id off an inbound
header. The runtime mints, exactly as it does today, and the id is **stamped on
the HTTP response** — where Traefik's access log already captures it.

That last clause is a measurement, not a hope. **D141 deferred it in Session 5**
— *"whether `X-Request-ID` can be retained as a response field is measured
against the locked digest before it is written, not read from a page"* — and
nothing measured it since. Rig E, against the locked `traefik:v3.7` digest:

| Key Traefik emits | Direction | Under the shipped policy |
|---|---|---|
| `request_X-Request-Id` | inbound, from the client | kept |
| `origin_X-Request-Id` | the response as the origin sent it | **kept** |
| `downstream_X-Request-Id` | the response as sent to the client | **kept** |

Measured with two controls: `request_Accept` is **dropped**, proving
`defaultMode: drop` is in force, and `RequestPath` is **dropped**, proving the
`names:` block is applied. So the arms are about the shipped configuration and
not about a permissive one the rig invented.

**The edge needs no change at all.** `infra/edge/traefik.yaml` already names
`X-Request-ID: keep`, and Traefik matches the header case-insensitively — the
config's `-ID` against the wire's `-Id` — which was a real risk and is now
measured rather than assumed (D274).

So the four legs close like this:

1. **ingress** — `downstream_X-Request-Id` in Traefik's access log
2. **API / agent** — the runtime's structured log line, same id
3. **upstream** — the `X-Request-Id` header on every PostgREST call
4. **audit** — `app_private.agent_audit.request_id`

**One mint, at the HTTP boundary.** The id is minted by an ASGI middleware
wrapping the app — the outermost place that corresponds one-to-one with an HTTP
request — and held in a `ContextVar` that `mcp_authorization._resolve` reads.
`_resolve` mints only if nothing stamped one, which keeps it correct when called
directly. `RefuseBrowserOrigins` is the precedent for the ASGI layer and the
reason it is plain ASGI rather than `BaseHTTPMiddleware`.

## Consequences

- **D478 is narrowed, not reversed.** Nothing at ingress mints, and nothing
  inbound is trusted. What changes is that ingress can now *record* an id it did
  not invent, because the response carries one.
- **A caller may still send `X-Request-Id`.** It is logged by Traefik as
  `request_X-Request-Id`, it reaches the database in
  `current_setting('request.headers')`, and **it is used for nothing.** An
  operator correlating by the `downstream_` key never sees it. That is worth
  stating because the header is not rejected: rejecting it would break clients
  that set one as a matter of course, and it costs nothing to ignore.
- The correlation an operator performs is `downstream_X-Request-Id` → the
  runtime's log → the audit row. Three sources, one value, none of them the
  caller's.
- **`OPS-LOG-001`'s ingress leg needs no Traefik change**, which means it also
  needs no edge restart and no ACME risk on the host trip.

## What this does not decide

**Whether the `database`-source audit row records the id.** That is D500 and
migration 0022, and it is Run 6's — including D633's guard, without which a
malformed header destroys the write it was meant to annotate.

**Whether a caller's own id should be recorded as a separate, untrusted field.**
There is a real use for it — a client correlating its own logs with this
deployment's — and it would be a *second* column, explicitly named as
caller-supplied, never joined to anything. Nobody has asked for it, and adding a
caller-writable field to an audit table is not something to do speculatively.
