"""Counts and durations over the record `mcp_telemetry` already produces.

**One source, two carriers** (ADR 0167). Every number here comes off the same
`Timed` that writes the log line — not from a second measurement of the same
call. That is the whole reason a metric may exist at all: the alternative is a
value computed twice, which this repository has already paid for once, when a
deploy called `backup_state` on a finished state block and published `failing`
for every project (D701).

**What is NOT here is the larger half, and it is a decision rather than a gap.**
Pooler saturation, live connection counts and transaction duration all need a
database credential, and a process holding one is a **sixth claimant on
`max_connections`** — a budget `config.connection_claimants` guards with a hard
preflight error, and one that took a whole run to move from four to five
(ADR 0148). Adding a claimant as a side effect of a metrics run is exactly the
unintended change that guard exists to prevent. Recorded rather than built.

Two rules make a label set here different from an attribute set on a span:

* **A label value is a series, and a series is memory.** The host has no swap
  (ADR 0165), so unbounded cardinality is not untidiness — it is an OOM whose
  victim the kernel picks. Every label here is drawn from a closed set, and a
  value outside it becomes `LABEL_OTHER` rather than a new series. The count
  stays honest; the cardinality stays bounded.
* **A label reaches `/metrics`, which is read by whoever holds the route's
  credential.** So `agent_id`, `owner_id`, `resource` and `request_id` are
  absent, and their absence is the point: `RECORD_FIELDS` has eight fields and
  this carrier takes two of them. An identity on a metrics surface is an
  identity published to every reader of that surface, for as long as the series
  lives.

**The exposed name is not the name written here**, and that is measured rather
than assumed. See `EXPOSED_METRIC_NAMES`.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "EXPOSED_METRIC_NAMES",
    "LABEL_OTHER",
    "METRIC_LABELS",
    "configure",
    "record",
]

#: Every label a metric here may carry, enumerated for `RECORD_FIELDS`' reason:
#: a shape nobody declared is a shape the canary is not checking.
#:
#: It is the telemetry record's field set minus six. `agent_id` and `owner_id`
#: are identities; `resource` names a table; `request_id` is unique per call and
#: would mint one series per request, which is the cardinality failure in its
#: purest form. `elapsed_ms` and `row_count` are values rather than labels —
#: they are what a histogram measures, not what it is keyed by.
METRIC_LABELS = ("outcome", "tool")

#: What a label value becomes when it is not in its closed set.
#:
#: **Substituted rather than dropped.** Dropping the observation would make an
#: unexpected tool name invisible, and "a call nobody counted" is a worse answer
#: than "a call counted under a name that says it was unexpected". Substituted
#: rather than passed through because a label value that a caller can influence
#: is a series a caller can create, and series are memory on a swapless host.
LABEL_OTHER = "other"

#: What each instrument is CALLED on the exposition surface, measured against
#: the pinned collector rather than derived from the OTLP name.
#:
#: **The rename is not cosmetic and a rule written against the source name
#: matches nothing.** Measured, pushing through the locked collector:
#:
#:   * `agent.tool_calls`, a counter with unit `1`, is served as
#:     **`agent_tool_calls_total`** — dots become underscores and a counter
#:     gains `_total`.
#:   * `agent.tool_call.duration`, a histogram with unit `ms`, is served as
#:     **`agent_tool_call_duration_milliseconds`** — the UNIT is expanded from
#:     its abbreviation and appended to the name. `ms` does not appear; the word
#:     does.
#:
#: This mapping is the contract Run 5's alert rules are written against, which
#: is why it is a declared constant with a test behind it rather than a comment.
#: Changing an instrument's unit here silently renames its series.
EXPOSED_METRIC_NAMES = {
    "agent.tool_calls": "agent_tool_calls_total",
    "agent.tool_call.duration": "agent_tool_call_duration_milliseconds",
}

#: How often the SDK pushes accumulated metrics to the collector, in seconds.
#:
#: **Explicit, because the default is 60 and the collector expires a series it
#: has not seen for 60** (`runtime_override.OTEL_METRIC_EXPIRATION_SECONDS`).
#: Measured in the SDK's own source: `export_interval_millis` falls back to
#: `OTEL_METRIC_EXPORT_INTERVAL` and then to `60000`. Left at the default, a
#: series would be expiring at exactly the cadence it is refreshed -- appearing
#: and vanishing from the exposition according to which of the two timers won,
#: and taking any rule written over it in and out with it.
#:
#: Four exports per expiration window, so it takes four CONSECUTIVE misses for
#: a series to drop -- which is the difference between "this process has
#: stopped" and "this process was briefly slow".
#:
#: `test_a_metric_series_is_refreshed_several_times_before_it_can_expire`
#: asserts that relationship across the two modules. It is one property held in
#: two processes' configuration, and nothing else would notice them drifting.
METRIC_EXPORT_INTERVAL_SECONDS = 15

_CALLS: Any | None = None
_DURATION: Any | None = None
_TOOL_NAMES: tuple[str, ...] = ()
_OUTCOMES: tuple[str, ...] = ()


def configure(
    *,
    endpoint: str | None,
    service_name: str,
    tool_names: tuple[str, ...],
    outcomes: tuple[str, ...],
) -> bool:
    """Wire the meter, or return False when no collector is configured.

    Mirrors `mcp_tracing.configure` exactly, including the reason for `None`
    over a discarding exporter: a deployment with no collector should cost
    nothing. The endpoint is a URL and not a credential, which is what lets it
    be an ordinary setting at all — the MCP runtime holds no credential, and a
    bearer token for a collector would be one.

    Returns whether metrics are on, so a caller can say so rather than infer it.

    **The two closed sets arrive here rather than being imported**, and the
    reason is a cycle that would otherwise be real: `mcp_tools` owns the tool
    roster and imports `mcp_telemetry`, which is where a completed call is
    recorded from. Importing either from here would close a loop. Taking them
    as arguments also keeps this module the owner of no roster at all — it
    constrains values against a list, and something else says what the list is
    (D486's rule, that two lists which must agree beat one list read twice).
    """
    global _CALLS, _DURATION, _TOOL_NAMES, _OUTCOMES
    _TOOL_NAMES = tool_names
    _OUTCOMES = outcomes
    if not endpoint:
        _CALLS = None
        _DURATION = None
        return False

    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource

    # `service.name` explicitly, for the reason `mcp_tracing.configure` gives:
    # the SDK's default is `unknown_service`, and a telemetry plane in which
    # every project calls itself the same thing has undone the per-project
    # separation ADR 0164 built.
    #
    # **And nothing else goes in the Resource.** Measured: every resource
    # attribute is served verbatim on the exposition surface as a label of a
    # synthesised `target_info` series. A Resource is not private metadata —
    # it is published, and it is published under a name nobody here chose.
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint),
        export_interval_millis=METRIC_EXPORT_INTERVAL_SECONDS * 1000,
    )
    provider = MeterProvider(
        resource=Resource.create({"service.name": service_name}),
        metric_readers=[reader],
    )
    meter = provider.get_meter("apg.mcp")
    _CALLS = meter.create_counter("agent.tool_calls", unit="1")
    # Milliseconds, because that is the unit the record already carries and
    # converting would create a second number for one duration. The unit is
    # part of the exposed name (see EXPOSED_METRIC_NAMES), so this is a
    # naming decision as much as a measurement one.
    _DURATION = meter.create_histogram("agent.tool_call.duration", unit="ms")
    return True


def _label(value: str, permitted: tuple[str, ...]) -> str:
    """Constrain one label value to its closed set."""
    return value if value in permitted else LABEL_OTHER


def record(*, tool: str, outcome: str, elapsed_ms: int) -> None:
    """Count one completed tool call, and observe how long it took.

    Called from `mcp_telemetry.Timed.__exit__` with the values that same record
    is about to log, so the two carriers cannot disagree about what happened.

    A no-op until `configure` has been given an endpoint, which is why this can
    sit in the hot path from this run rather than waiting for one.
    """
    calls, duration = _CALLS, _DURATION
    if calls is None or duration is None:
        return

    labels = {
        "tool": _label(tool, _TOOL_NAMES),
        "outcome": _label(outcome, _OUTCOMES),
    }
    # The label set is asserted rather than trusted. It is built two lines
    # above, so today this cannot fail -- and it is here because the next
    # person to add a dimension will add it to the dict, and this is what
    # turns that into an error instead of a new published label.
    unknown = sorted(set(labels) - set(METRIC_LABELS))
    if unknown:
        raise ValueError(f"{unknown} are not declared metric labels")

    calls.add(1, labels)
    # Keyed by tool only. Adding `outcome` here would multiply the bucket count
    # by three for a question nobody asked: how long a refusal took is answered
    # by the counter's rate, and a histogram is the expensive instrument.
    duration.record(elapsed_ms, {"tool": labels["tool"]})
