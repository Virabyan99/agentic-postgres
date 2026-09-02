"""Spans over the id this deployment already mints (ADR 0166).

**A transport, not an identifier.** `OPS-LOG-001` has been proved since Session
11: one request id spans ingress, the agent plane, the upstream call and the
audit row. This module gives that correlation an OTLP shape so a collector can
receive it. It does not create a second value, and the reason it cannot is
arithmetic rather than discipline -- **a W3C trace id is 16 bytes and a `uuid4`
is 16 bytes**, so `request_id.current_request_id()` becomes the trace id
directly. Measured: the span's trace id renders as the request id's hex and
parses back to the same UUID.

A future reader who "adds a trace id" here has not added a field. They have
created the second authority ADR 0002 exists to prevent.

**Nothing reads an inbound `traceparent`.** ADR 0160 refused inbound identity
with a reason that has not changed: an id a caller chose lets one agent stamp
its actions with another agent's id, and an operator reading the audit trail by
request would see a second agent's writes inside a first agent's request. W3C
trace context propagates the other way by design, and adopting it unexamined
would have reversed that decision as a side effect of choosing a format.

**Two SDK defaults are off, and D773 is why.** Measured against
`opentelemetry-sdk` 1.44.0 with a planted canary and a clean control: an
exception merely *escaping* a span makes the SDK attach `exception.message`,
`exception.stacktrace` and a `status.description` containing the message.
`record_exception` and `set_status_on_exception` both default to **on**.

`mcp_telemetry` refuses precisely this for log records -- *"an unclassified
failure is logged with the exception's TYPE and never its message, because a
message is where a caller's value would be if one ever reached one."* The span
carrier arrives with that refusal reversed, so this module turns both defaults
off and enumerates what an attribute may be called.

**No auto-instrumentation.** The instrumentation packages attach `http.url` to
client spans as a matter of course, and a URL is on the canary's list. Spans
here are written by hand from values the telemetry record already carries.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app import request_id as request_id_module

__all__ = [
    "SPAN_ATTRIBUTES",
    "SPAN_NAMES",
    "RequestIdGenerator",
    "configure",
    "span",
    "trace_id_for",
]

#: Every attribute name a span may carry, enumerated for `RECORD_FIELDS`'
#: reason: a shape nobody declared is a shape the canary is not checking.
#:
#: It is deliberately the telemetry record's field set minus `request_id`.
#: `request_id` is absent because it is not an attribute here -- it IS the trace
#: id, and writing it twice would put the same value in two places that could
#: later disagree.
SPAN_ATTRIBUTES = (
    "agent_id",
    "elapsed_ms",
    "outcome",
    "owner_id",
    "resource",
    "row_count",
    "tool",
)

#: Span names, closed. A name is not a value a caller supplies, but it is a
#: string that reaches the telemetry plane, and an unclosed set is one an
#: author could interpolate a resource into without noticing.
#:
#: `outbound` rather than `upstream`, and it is not only to keep a text scan
#: quiet. **`upstream` is a term of art in this service**: it is the capability
#: lock's PUBLISHED identity, which ADR 0126 says must never be dialled, and
#: `test_nothing_dials_the_locks_published_upstream` refuses any line containing
#: `.upstream` in an `mcp_*.py` file. A span called `agent.upstream_call` tripped
#: it -- a false positive, since a string literal dials nothing, and D464's
#: recorded shape (a text scan standing in for a construct).
#:
#: The name moved rather than the scan, deliberately. Loosening a guard that
#: protects a real boundary to admit a name this module chose freely would be
#: trading a security control for a preference -- and `outbound` is the clearer
#: word anyway, because in this codebase `upstream` already means something else.
SPAN_NAMES = ("agent.tool_call", "agent.outbound_call")

#: A trace id of all zeros is invalid under the W3C specification and is
#: silently dropped by collectors. `uuid4` cannot produce one, but this module
#: converts whatever it is handed, so the check is here rather than assumed.
_INVALID_TRACE_ID = 0


def trace_id_for(request_id: str) -> int:
    """The request id as a W3C trace id.

    Raises rather than substituting a random id on bad input. A generated
    fallback would be a second identifier created at the exact moment
    correlation was needed, and it would look like it worked.
    """
    parsed = uuid.UUID(request_id)
    value = int(parsed.hex, 16)
    if value == _INVALID_TRACE_ID:
        raise ValueError("a request id of all zeros is not a valid trace id")
    return value


class RequestIdGenerator:
    """Trace ids come from the request; span ids are random.

    Implements the SDK's `IdGenerator` interface without importing it, so this
    module is importable and testable in an environment that has no
    OpenTelemetry installed -- which is every environment until the session-14
    image is built. `configure` does the real wiring and is the only place the
    SDK is touched.

    `generate_trace_id` falls back to a random id ONLY outside an HTTP request,
    where there is no request id to use and nothing to correlate with. Inside a
    request the id is the request's, always.

    **The interface has three methods, not two**, and that was found by running
    against the real SDK rather than by reading it: `TracerProvider` calls
    `is_trace_id_random()` on every root span, and a duck-typed generator
    missing it raises `AttributeError` deep inside span creation. The first
    version of this class had two methods and every offline test that did not
    build a real span passed. That is the gap between *will this run* and *is
    what it asserts true*, and only the real library closed it.
    """

    def generate_trace_id(self) -> int:
        current = request_id_module.current_request_id()
        if current is None:
            # No HTTP request in scope -- a startup or background span. There is
            # nothing to correlate to, so a random id is honest here in a way it
            # would not be inside a request.
            return int(uuid.uuid4().hex, 16)
        return trace_id_for(current)

    def generate_span_id(self) -> int:
        return int(uuid.uuid4().hex[:16], 16)

    def is_trace_id_random(self) -> bool:
        """True, and it is a claim about uuid4 rather than a convenience.

        The SDK asks this to decide whether the trace id carries the randomness
        W3C requires for consistent sampling, which lives in the **rightmost 56
        bits**. A uuid4 fixes only its version nibble (byte 6) and two variant
        bits (byte 8); bytes 9-15 are random, so the rightmost 56 bits are
        entirely random and the answer is honestly yes.

        Both paths above produce a uuid4 -- the request id is one, and the
        fallback mints one -- so there is no case where this would need to
        differ. If a future change ever derives a trace id from something that
        is not a uuid4, this method is the first thing that stops being true.
        """
        return True


_TRACER: Any | None = None


def configure(*, endpoint: str | None, service_name: str) -> Any | None:
    """Wire a tracer, or return None when no collector is configured.

    `None` rather than a no-op exporter that drops on the floor: a deployment
    with no collector should cost nothing, and a silently-discarding exporter is
    a process doing work whose output nobody receives.

    The endpoint is a URL and not a credential. That distinction is the reason
    it may be an ordinary setting at all -- a bearer token for a collector would
    be a credential, and the MCP runtime holds none.
    """
    global _TRACER
    if not endpoint:
        _TRACER = None
        return None

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # `service.name` explicitly. The SDK's default is `unknown_service`, and a
    # telemetry plane in which every project calls itself the same thing has
    # undone the per-project separation ADR 0164 built.
    provider = TracerProvider(
        id_generator=RequestIdGenerator(),
        resource=Resource.create({"service.name": service_name}),
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    _TRACER = provider.get_tracer("apg.mcp")
    return _TRACER


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[None]:
    """One span, carrying only enumerated attributes and no exception text.

    Refuses an unknown name or attribute rather than dropping it. A silently
    ignored attribute is how a caller value reaches a carrier nobody is
    checking, and the canary asserts the declared set rather than grepping for
    what it fears.

    `record_exception=False` and `set_status_on_exception=False` are D773: with
    the defaults, an exception escaping this block would attach its message and
    its stacktrace. The exception still propagates -- it is simply not
    *described* to the telemetry plane, which is what `mcp_telemetry` already
    does for log records.
    """
    if name not in SPAN_NAMES:
        raise ValueError(f"{name!r} is not a declared span name")
    unknown = sorted(set(attributes) - set(SPAN_ATTRIBUTES))
    if unknown:
        raise ValueError(f"{unknown} are not declared span attributes")

    tracer = _TRACER
    if tracer is None:
        yield
        return

    with tracer.start_as_current_span(
        name,
        record_exception=False,
        set_status_on_exception=False,
    ) as active:
        for key, value in attributes.items():
            if value is not None:
                active.set_attribute(key, value)
        yield
