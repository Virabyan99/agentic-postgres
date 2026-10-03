"""The request and worker lines reach stdout, once each (OPS-LOG-001, ADR 0249).

D1918: the service wrote `apg.http.request` and `apg.mcp.read` at INFO and nothing
printed them -- no handler anywhere under `services/auth-api/app/`, so Python's
last-resort handler dropped everything below WARNING. Rig 36c measured it
through the image's uvicorn argv (0 lines as the tree was; one per request with
the handler). These proofs read the STREAM (`capsys`), never `caplog`: a record
that reaches a handler nobody prints is the defect, so the stream is the thing.

Each proof starts and ends with no handler of ours on either logger: a
`StreamHandler` binds `sys.stdout` when it is created, and `capsys` replaces
`sys.stdout` per test.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
import pytest

from app import log_setup, main
from app import workflow_worker as worker

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

PLANTED_TOKEN = "planted-token-0f3a9c"  # noqa: S105 -- a canary, not a credential
PLANTED_QUERY = "planted-query-77d1"
PLANTED_BODY = "planted-body-5e20"
PLANTED_PATH = "planted-path-a41b"
CALLER_ID = "00000000-0000-4000-8000-0000000000aa"


def _strip() -> None:
    for name in log_setup.LOGGERS:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            if getattr(handler, log_setup.MARKER, False):
                logger.removeHandler(handler)
        logger.propagate = True
        logger.setLevel(logging.NOTSET)


@pytest.fixture(autouse=True)
def clean_loggers() -> Any:
    _strip()
    yield
    _strip()


def _call(application: Any, method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://auth.invalid") as http:
            return await http.request(method, path, **kwargs)

    return asyncio.run(run())


def _request_lines(out: str) -> list[dict[str, Any]]:
    return [
        json.loads(line.split(" ", 1)[1])
        for line in out.splitlines()
        if line.startswith("apg.http.request ")
    ]


def test_create_app_installs_one_handler_on_each_logger() -> None:
    """`create_app` called twice -- and in a second mode -- still leaves ONE
    marked handler on each logger, at INFO, with propagation left ON (D2017)."""
    main.create_app("auth")
    main.create_app("auth")
    main.create_app("storage")
    for name in log_setup.LOGGERS:
        logger = logging.getLogger(name)
        marked = [h for h in logger.handlers if getattr(h, log_setup.MARKER, False)]
        assert len(marked) == 1, f"{name} carries {len(marked)} handlers of ours"
        assert logger.level == logging.INFO
        assert logger.propagate is True, f"{name} stopped propagating; caplog canaries go blind"


def test_a_request_prints_one_line_with_the_template_and_no_caller_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One line per request, carrying the route TEMPLATE and the plane's own
    request id -- the one the response hands back -- and none of what the caller
    planted: a bearer token, a query string, a body, a path, its own request id.

    The 404 is the control that the template is read from the matched route:
    an unmatched request is `<unmatched>`, never the path it asked for.
    """
    application = main.create_app("auth")
    planted = {"Authorization": f"Bearer {PLANTED_TOKEN}", "X-Request-Id": CALLER_ID}
    live = _call(application, "GET", f"/health/live?secret={PLANTED_QUERY}", headers=planted)
    missing = _call(
        application, "POST", f"/no/such/{PLANTED_PATH}", headers=planted, content=PLANTED_BODY
    )
    out = capsys.readouterr().out

    lines = _request_lines(out)
    assert len(lines) == 2, out
    assert [line["route"] for line in lines] == ["/health/live", "<unmatched>"]
    assert [line["status"] for line in lines] == [200, 404]
    assert [line["request_id"] for line in lines] == [
        live.headers["X-Request-Id"],
        missing.headers["X-Request-Id"],
    ]
    for value in (PLANTED_TOKEN, PLANTED_QUERY, PLANTED_BODY, PLANTED_PATH, CALLER_ID):
        assert value not in out, f"{value} reached the log"


def test_the_worker_logger_prints_info(capsys: pytest.CaptureFixture[str]) -> None:
    """D1837: the worker's INFO lines were invisible too. The idle withdrawal's
    line is printed through the real code path that writes it."""

    class Repository:
        async def withdraw_ended_approvals(self) -> int:
            return 3

    main.create_app("auth")
    asyncio.run(worker._withdraw_ended_approvals(Repository()))
    out = capsys.readouterr().out
    assert out.splitlines() == ['workflow.approvals_withdrawn {"count": 3}'], out


def test_no_line_is_printed_twice(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    """One request, ONE line on stdout -- and the record still reaches the root
    logger, so the `caplog` canaries that guard these lines' content keep seeing
    them (D2017). `create_app` puts no handler on the root logger: a line can
    only be doubled by a root handler, and the image installs none."""
    root = logging.getLogger()
    before = list(root.handlers)
    with caplog.at_level(logging.INFO, logger="apg.http"):
        application = main.create_app("auth")
        _call(application, "GET", "/health/live")
    assert root.handlers == before, "create_app attached a handler to the root logger"
    out = capsys.readouterr().out
    assert len(_request_lines(out)) == 1, out
    captured = [r for r in caplog.records if r.getMessage().startswith("apg.http.request ")]
    assert len(captured) == 1, "the request record did not propagate to the root logger"
