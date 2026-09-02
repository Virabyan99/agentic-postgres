"""The trace id is the request id, and a span carries only what it was given.

ADR 0166, and the canary extended to the span carrier (D773). These run without
OpenTelemetry installed: `mcp_tracing` touches the SDK only inside `configure`,
so everything the canary cares about -- the enumerated sets, the refusals, and
the identity relationship -- is testable in the checkout.
"""

from __future__ import annotations

import uuid

import pytest

from app import mcp_tracing, request_id
from app.mcp_telemetry import RECORD_FIELDS

pytestmark = [pytest.mark.contract, pytest.mark.p0]


# ---------------------------------------------------------------------------
# One identifier, not two
# ---------------------------------------------------------------------------


def test_the_trace_id_is_the_request_id_and_parses_back() -> None:
    """No second value exists, so there is nothing to keep in step (ADR 0166).

    A W3C trace id is 16 bytes and a uuid4 is 16 bytes. That is why this is an
    identity rather than a mapping -- and why a future reader who adds a
    separate trace id has created the second authority ADR 0002 forbids.
    """
    minted = request_id.mint()
    trace_id = mcp_tracing.trace_id_for(minted)

    rendered = format(trace_id, "032x")
    assert rendered == uuid.UUID(minted).hex
    assert str(uuid.UUID(hex=rendered)) == minted


def test_an_all_zero_trace_id_is_refused_rather_than_replaced() -> None:
    """A zero trace id is invalid under W3C and collectors drop it silently.

    Refused rather than substituted: a generated fallback would be a second
    identifier created at the exact moment correlation was needed, and it would
    look like it had worked.
    """
    with pytest.raises(ValueError, match="all zeros"):
        mcp_tracing.trace_id_for("00000000-0000-0000-0000-000000000000")


def test_a_trace_id_outside_a_request_is_random_rather_than_wrong() -> None:
    """Outside an HTTP request there is nothing to correlate to.

    A startup or background span gets a random trace id, which is honest. Inside
    a request it is the request's, always -- and that is the case the next test
    pins.
    """
    generator = mcp_tracing.RequestIdGenerator()
    assert request_id.current_request_id() is None
    first = generator.generate_trace_id()
    second = generator.generate_trace_id()
    assert first != second


def test_inside_a_request_every_span_gets_that_requests_id() -> None:
    """The property `OPS-LOG-001` is about, at the span layer."""
    minted = request_id.mint()
    token = request_id._CURRENT.set(minted)
    try:
        generator = mcp_tracing.RequestIdGenerator()
        assert format(generator.generate_trace_id(), "032x") == uuid.UUID(minted).hex
        # Twice, because a generator that minted per call would pass a single
        # read and produce two traces for one request.
        assert format(generator.generate_trace_id(), "032x") == uuid.UUID(minted).hex
    finally:
        request_id._CURRENT.reset(token)


def test_span_ids_are_not_the_trace_id() -> None:
    """A span id is 8 bytes and must vary; only the TRACE id is the request's."""
    generator = mcp_tracing.RequestIdGenerator()
    ids = {generator.generate_span_id() for _ in range(8)}
    assert len(ids) == 8
    assert all(value < 2**64 for value in ids)


# ---------------------------------------------------------------------------
# The canary, extended to the span carrier (D773)
# ---------------------------------------------------------------------------


def test_a_span_may_not_carry_a_token_a_url_or_any_caller_value() -> None:
    """**The canary's list, asserted against the span carrier.**

    `mcp_telemetry`'s list is: a token, a URL, an object key, or ANY caller
    value -- a filter operand, a column projection, or a row. The span carrier
    is new and its declared attribute set has to answer to the same list.
    """
    forbidden = {"token", "url", "object_key", "filters", "rows", "value", "message"}
    assert not forbidden & set(mcp_tracing.SPAN_ATTRIBUTES)


def test_the_span_attribute_set_is_the_records_minus_the_trace_id() -> None:
    """One list, two carriers, and the one difference is deliberate.

    `request_id` is a telemetry FIELD and is not a span attribute, because on a
    span it is the trace id. Writing it as an attribute as well would put one
    value in two places that could later disagree -- and a reader would have no
    way to tell which was authoritative.
    """
    assert set(mcp_tracing.SPAN_ATTRIBUTES) == set(RECORD_FIELDS) - {"request_id"}


def test_an_undeclared_attribute_is_refused_rather_than_dropped() -> None:
    """Refused, because a silently ignored attribute is how a leak arrives.

    The failure mode this prevents is not a crash. It is an author adding
    `url=...` to a span, seeing no error, and believing the value is being
    recorded somewhere harmless.
    """
    with pytest.raises(ValueError, match="not declared span attributes"):
        with mcp_tracing.span("agent.tool_call", url="https://canary.example/x"):
            pass


def test_an_undeclared_span_name_is_refused() -> None:
    """A name is a string that reaches the plane, and an open set is one an
    author could interpolate a resource into."""
    with pytest.raises(ValueError, match="not a declared span name"):
        with mcp_tracing.span("agent.notes_for_owner_42"):
            pass


def test_a_declared_span_is_a_no_op_when_no_collector_is_configured() -> None:
    """No collector means no cost, and no silently-discarding exporter.

    A deployment through session 13 has no collector at all, and this must not
    be the thing that makes it fail.
    """
    mcp_tracing.configure(endpoint=None, service_name="apg-test")
    with mcp_tracing.span("agent.tool_call", tool="notes_search", outcome="served"):
        pass


def test_configure_returns_none_without_an_endpoint() -> None:
    """The absence is reported rather than faked."""
    assert mcp_tracing.configure(endpoint=None, service_name="apg-test") is None


# ---------------------------------------------------------------------------
# The canary against a REAL span (D773)
# ---------------------------------------------------------------------------


def _capture_spans(monkeypatch: pytest.MonkeyPatch) -> list:
    """A real TracerProvider with an in-memory exporter, wired into the module.

    The SDK is real on purpose. The whole question D773 asks is what the actual
    library does when nobody tells it otherwise, and a stand-in would do
    whatever its author believed the defaults were -- which is precisely the
    belief the measurement overturned (ADR 0065).
    """
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

    captured: list = []

    class Capture(SpanExporter):
        def export(self, spans):  # type: ignore[no-untyped-def]
            captured.extend(spans)
            return SpanExportResult.SUCCESS

        def shutdown(self) -> None:
            return None

    provider = TracerProvider(id_generator=mcp_tracing.RequestIdGenerator())
    provider.add_span_processor(SimpleSpanProcessor(Capture()))
    monkeypatch.setattr(mcp_tracing, "_TRACER", provider.get_tracer("apg.test"))
    return captured


def test_an_escaping_exception_puts_no_message_on_a_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The canary, against the span carrier.**

    A value that exists only because this test made it is put inside an
    exception that escapes a span. `mcp_telemetry` refuses to log an exception's
    message because "a message is where a caller's value would be"; this asserts
    the span carrier refuses it too.

    The control is the next test, and it is what makes this one mean something:
    with the SDK's own defaults the same value DOES appear. Without that arm,
    this test passes equally well against a rig that never recorded anything.
    """
    captured = _capture_spans(monkeypatch)
    canary = "APG-CANARY-presigned-url-and-token-a7f3e91c"

    with pytest.raises(ValueError):
        with mcp_tracing.span("agent.tool_call", tool="notes_search"):
            raise ValueError(f"failed fetching {canary}")

    assert captured, "no span was exported at all, so nothing was measured"
    blob = "".join(span.to_json() for span in captured)
    assert canary not in blob, (
        "an escaping exception put its message on the span. record_exception and "
        "set_status_on_exception default to ON (D773), so this is what happens "
        "when either default is restored"
    )
    assert "exception.stacktrace" not in blob
    assert "exception.message" not in blob


def test_the_sdk_defaults_would_have_leaked_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """**THE CONTROL**, and it is the reason the test above is evidence.

    The same exception, the same canary, through the SDK's own defaults rather
    than through `mcp_tracing.span`. The leak must APPEAR here. If it does not,
    the guard above is passing because the rig records nothing, and the
    protection it claims to prove is unmeasured.

    This is a control that can fail for the reason it is watching for (D509),
    which the version that only asserted absence could not.
    """
    captured = _capture_spans(monkeypatch)
    canary = "APG-CANARY-presigned-url-and-token-a7f3e91c"

    tracer = mcp_tracing._TRACER
    assert tracer is not None
    with pytest.raises(ValueError):
        # No record_exception=False, no set_status_on_exception=False: the
        # defaults, which is the configuration mcp_tracing.span overrides.
        with tracer.start_as_current_span("control"):
            raise ValueError(f"failed fetching {canary}")

    blob = "".join(span.to_json() for span in captured)
    assert canary in blob, (
        "the SDK's defaults did NOT leak the message, so this control cannot "
        "fail for the reason it watches for -- and the guard beside it is "
        "proving nothing (D509)"
    )
    assert "exception.stacktrace" in blob


def test_a_real_span_carries_the_requests_trace_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end at the span layer: one id, taken from the request."""
    captured = _capture_spans(monkeypatch)
    minted = request_id.mint()
    token = request_id._CURRENT.set(minted)
    try:
        with mcp_tracing.span("agent.tool_call", tool="notes_search", outcome="served"):
            pass
    finally:
        request_id._CURRENT.reset(token)

    assert len(captured) == 1
    rendered = format(captured[0].get_span_context().trace_id, "032x")
    assert rendered == uuid.UUID(minted).hex


def test_a_real_span_carries_only_the_attributes_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the code PRODUCES, not which names appear in it (D277)."""
    captured = _capture_spans(monkeypatch)
    with mcp_tracing.span("agent.tool_call", tool="notes_search", outcome="served", row_count=3):
        pass

    attributes = dict(captured[0].attributes or {})
    assert set(attributes) == {"tool", "outcome", "row_count"}
    assert set(attributes) <= set(mcp_tracing.SPAN_ATTRIBUTES)
