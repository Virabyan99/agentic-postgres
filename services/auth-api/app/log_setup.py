"""One stdout handler for the lines this service already writes (ADR 0249, D1918).

`apg.http.request` (the middleware in `main.py`), `apg.mcp.read`
(`mcp_telemetry.py`) and the workflow worker's `app.workflow_worker` lines were
designed to be safe to print -- a route TEMPLATE, a minted request id, fixed
field sets -- and until 1.14.0 none of them was printed: nothing configured a
handler, so an INFO record reached only Python's last-resort handler, which
prints WARNING and above. Rig 36c measured it through the image's own uvicorn
argv: 0 lines as the tree was, exactly one per request with this installed.

Three properties, each proved in `tests/contract/test_request_log.py`:

* **idempotent** -- the handler carries a marker, and a logger that already
  holds a marked handler gains none, so `create_app` called twice installs one;
* **propagation is left ON** (D2017) -- nothing in the image puts a handler on
  the root logger (rig 36c re-measured one line per request with propagation
  on), and turning it off would blind every `caplog` canary that reads these
  loggers (`test_mcp_budgets.py`, `test_mcp_tools.py`, `test_connector_delivery.py`)
  the moment any test in the process had built an application;
* **nothing else** -- no field is added to any line, no other logger is touched,
  and uvicorn's own logging is left as uvicorn configured it.

**Since Session 42 (ADR 0277, D2575)** the same records are also exported over
OTLP to the project's own collector when `APG_OTLP_LOGS_ENDPOINT` is set --
the message and its level and nothing else, through a bounded batch processor
that never blocks a request. The collector stamps the project; the telemetry
plane holds the lines for the operator.
"""

from __future__ import annotations

import logging
import os
import sys

#: The loggers whose INFO lines are printed. `apg` is the parent of `apg.http`
#: and `apg.mcp`; the worker logs under its module's name (D1837).
LOGGERS = ("apg", "app.workflow_worker")

#: The marker on a handler this module installed. An attribute rather than a
#: type check, so a reload of this module still recognises its own handler.
MARKER = "_apg_stdout"

#: Session 42 (ADR 0277, D2575): the SAME lines, also exported over OTLP to this
#: project's own collector when `APG_OTLP_LOGS_ENDPOINT` is set (compose sets it
#: to `http://metrics:4318/v1/logs` on every service that runs `create_app`).
OTLP_ENDPOINT_VARIABLE = "APG_OTLP_LOGS_ENDPOINT"
OTLP_MARKER = "_apg_otlp"
#: The batch processor's bounds: a full queue drops a line, never blocks one.
OTLP_QUEUE = 2048
OTLP_BATCH = 256
OTLP_EXPORT_TIMEOUT_MS = 2000


class OtlpLineHandler(logging.Handler):
    """One D1918 line in, one OTLP log record out: **the message and its level,
    nothing else** (D2575).

    Written here rather than taken from `opentelemetry-sdk`'s `LoggingHandler`
    for two measured reasons (Session 42 Run 5, D2613): that handler is
    DEPRECATED in the pinned 1.44.0 (it points at a separate instrumentation
    package), and it adds attributes of its own -- the source file, the line,
    the thread and an exception's type, message and traceback. The body here is
    `record.getMessage()`, never `format()`: a formatter appends `exc_info` and
    `stack_info`, and a traceback is where a caller's value would hide. The
    record carries no attribute; the scope is the logger's name.

    `emit` hands the record to the SDK's batch processor, which queues it in
    memory and exports from its own thread -- a slow or absent collector costs
    a request nothing (`test_a_slow_exporter_does_not_block_a_request`), and a
    full queue drops the line (optional detail, ADR 0277).
    """

    def __init__(self, provider: object) -> None:
        super().__init__(level=logging.INFO)
        self._provider = provider
        setattr(self, OTLP_MARKER, True)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            from opentelemetry._logs import LogRecord, SeverityNumber

            severity = {
                logging.DEBUG: SeverityNumber.DEBUG,
                logging.INFO: SeverityNumber.INFO,
                logging.WARNING: SeverityNumber.WARN,
                logging.ERROR: SeverityNumber.ERROR,
                logging.CRITICAL: SeverityNumber.FATAL,
            }.get(record.levelno, SeverityNumber.INFO)
            self._provider.get_logger(record.name).emit(  # type: ignore[attr-defined]
                LogRecord(
                    timestamp=int(record.created * 1e9),
                    body=record.getMessage(),
                    severity_text=record.levelname,
                    severity_number=severity,
                )
            )
        except Exception:
            self.handleError(record)


def otlp_provider(endpoint: str, *, exporter: object | None = None, mode: str = "") -> object:
    """A `LoggerProvider` exporting to ``endpoint`` through the bounded batch
    processor. ``exporter`` replaces the OTLP exporter in a test. The resource
    names the service mode; the project is stamped by the collector, never
    here (ADR 0277: the platform names the project, not the payload)."""
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import Resource

    if exporter is None:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

        exporter = OTLPLogExporter(endpoint=endpoint, timeout=OTLP_EXPORT_TIMEOUT_MS / 1000)
    provider = LoggerProvider(resource=Resource.create({"service.name": mode or "auth-api"}))
    provider.add_log_record_processor(
        BatchLogRecordProcessor(
            exporter,  # type: ignore[arg-type]
            max_queue_size=OTLP_QUEUE,
            max_export_batch_size=OTLP_BATCH,
            export_timeout_millis=OTLP_EXPORT_TIMEOUT_MS,
        )
    )
    return provider


def configure_logging(
    environ: dict[str, str] | None = None, *, exporter: object | None = None
) -> None:
    """Attach one stdout handler at INFO to each logger in `LOGGERS`, once --
    and, when `APG_OTLP_LOGS_ENDPOINT` is set, one `OtlpLineHandler` beside it,
    once (Session 42). ``environ`` and ``exporter`` exist for a test."""
    env = os.environ if environ is None else environ
    endpoint = env.get(OTLP_ENDPOINT_VARIABLE, "")
    provider = None
    for name in LOGGERS:
        logger = logging.getLogger(name)
        if not any(getattr(handler, MARKER, False) for handler in logger.handlers):
            handler = logging.StreamHandler(sys.stdout)
            # The lines already begin with their own name (`apg.http.request {...}`).
            handler.setFormatter(logging.Formatter("%(message)s"))
            setattr(handler, MARKER, True)
            logger.addHandler(handler)
        if endpoint and not any(getattr(h, OTLP_MARKER, False) for h in logger.handlers):
            if provider is None:
                provider = otlp_provider(endpoint, exporter=exporter, mode=env.get("APP_MODE", ""))
            logger.addHandler(OtlpLineHandler(provider))
        logger.setLevel(logging.INFO)
