# 0166 — The trace id is the request id, and a span carries only what it was given

- **Status:** accepted
- **Date:** 2026-09-02
- **Session:** 14, Run 3 (`OPS-LOG-001`, `OPS-REDACT-001`, D763)
- **Related:** **D773** (measured: an exception escaping a span attaches its
  message and stacktrace, by default), **D763** (correlation already exists and
  is proved), ADR 0160 (**the request id flows outward and no caller value is
  ever trusted**), ADR 0130/0141 (what a telemetry record is, and what it may
  never carry), ADR 0002 (one derivation per identity), ADR 0164 (the collector
  these spans reach), D449 (a logged traceback carries no caller data *because a
  default is off*), D633/D478 (what a caller-supplied request id has cost).

## Context

The Stage 2 specification asks for *"OpenTelemetry propagation through Traefik,
FastAPI, FastMCP and protected downstream HTTP calls."* Read plainly that is a
request to build request correlation. **This deployment already has it** (D763):
one id spans ingress → FastMCP → PostgREST → `app_private.agent_audit.request_id`,
proved as `OPS-LOG-001` since Session 11.

So the question is not how to correlate. It is how to adopt a transport without
acquiring a **second** identifier, and without the new carrier undoing a
redaction rule the old one enforces.

Two facts make that sharp.

**ADR 0160 refused inbound identity, with a reason.** *"The id flows outward, not
inward. Nothing reads a request id off an inbound header."* An id a caller chose
lets one agent stamp its actions with another agent's id, and an operator reading
the audit trail by request sees a second agent's writes inside a first agent's
request. D633 is the same family measured a run earlier: a caller-supplied
`X-Request-Id` reaching an unguarded cast rolled the caller's own write back.

**W3C trace context works the other way.** Its whole propagation model is to read
`traceparent` off an inbound request and continue the caller's trace. Adopting
that unexamined would reverse ADR 0160 as a side effect of choosing a telemetry
format.

## Decision

**1. The trace id IS the request id. There is no second identifier.**

A W3C trace id is 16 bytes; a `uuid4` is 16 bytes. The existing `request_id.mint()`
value becomes the trace id directly, through a custom `IdGenerator`. Measured:
the span's trace id renders as the request id's hex exactly, and parses back to
the same UUID.

```
request_id        04c99bdc-ebce-4e2e-868a-ff61026fe9a9
span trace_id     04c99bdcebce4e2e868aff61026fe9a9
round-trips back  True
```

This is D763's requirement satisfied by construction rather than by discipline:
**there is nothing to keep in step**, because there are not two values. A future
reader who "adds a trace id" has not added a field, they have created the second
authority ADR 0002 exists to prevent.

**2. Nothing reads an inbound `traceparent`.** ADR 0160 is not weakened to
accommodate a format. A caller who supplies one is answered normally and their
header is used for nothing — the same treatment `request_X-Request-Id` already
gets at the edge. The deployment starts its own trace at its own boundary, which
is the only boundary whose identities it can vouch for.

**3. Span attributes are ENUMERATED, and the two exception defaults are off.**

This is the half that would otherwise have gone wrong silently. Measured against
`opentelemetry-sdk` 1.44.0, with a planted canary and a clean control span:

| What the code did | What the span carried |
|---|---|
| let an exception escape the span | `exception.message`, `exception.stacktrace`, `status.description` |
| called `record_exception` explicitly | the same, plus `exception.escaped` |
| **control** — never saw the value | nothing |

`record_exception` and `set_status_on_exception` **default to on**. So an
exception escaping a span publishes its message and traceback to the telemetry
plane with nobody having written a line of code to make that happen.

`mcp_telemetry` refuses exactly this for log records: *"an unclassified failure
is logged with the exception's TYPE and never its message, because a message is
where a caller's value would be if one ever reached one."* **The span carrier
arrives with that refusal reversed.** Both defaults are therefore turned off, a
span's attribute names are enumerated the way `RECORD_FIELDS` enumerates a log
record's, and a status is set from a *classified outcome* rather than from an
exception.

**4. Auto-instrumentation is not adopted.** The instrumentation packages attach
`http.url` and `http.target` to client spans as a matter of course, and a URL is
on the canary's list. This deployment's spans are written by hand, from the same
enumerated values the telemetry record already carries.

**5. The canary is extended to spans in this run**, not a later one — a
telemetry plane that ships spans is a second place a presigned URL can reach, and
Session 7's canary exists because one did.

## Consequences

Makes easy:

- An operator reading a trace, a log line, an access log entry and an audit row
  is reading **one id**, with no join table and no mapping.
- The forbidden list has one meaning across both carriers, and one test asserts
  it for both.
- Removing OpenTelemetry later removes a transport and no identity.

Makes hard:

- **Spans are written by hand.** No automatic HTTP or framework spans, so a new
  outbound call that should be traced is an edit rather than a side effect. That
  is the intended trade: the same property means a new outbound call cannot
  publish its URL by accident.
- A caller who legitimately wants their trace continued cannot have it. That is
  ADR 0160's cost, already paid and re-affirmed here rather than re-litigated.

Residual, named:

- The SDK's default resource attaches `service.instance.id`, **a random uuid it
  mints per process**. It is not a caller value and identifies a process rather
  than a request, so it is left alone — but it is a second identifier in the
  payload and this sentence is where a future reader learns it was noticed
  rather than missed.
- `service.name` defaults to `unknown_service`. It is set explicitly per project,
  because a telemetry plane in which every project calls itself the same thing
  has undone the per-project separation ADR 0164 built.

## Alternatives considered

**Honour an inbound `traceparent`, mint when absent.** Rejected: it is ADR 0160's
rejected design wearing a different header name, and the reason ADR 0160 gave
applies unchanged — it lets a caller choose the identifier under which this
deployment files its own audit records.

**Mint a separate trace id and carry the request id as a span attribute.**
Rejected. It works, and it is what most deployments do. It also produces two
identifiers for one request, which is the exact shape ADR 0002 forbids and which
this repository has paid for twice in one session (D680, D682). The uuid/trace-id
size match makes the second identifier unnecessary, so accepting one would be
choosing a defect that a measurement showed was avoidable.

**Adopt the OpenTelemetry instrumentation packages.** Rejected on the canary's
list: they attach `http.url`, which is a forbidden value, and they would do it
for every downstream call automatically. A telemetry surface that redacts by
default and a framework that publishes by default cannot both be in charge.

**Leave exception recording on and scrub the message.** Rejected: it makes the
redaction a filter over a value that was already collected, and the filter would
have to be right about every framework's exception text for ever. Not collecting
it is a property; scrubbing it is a promise.
