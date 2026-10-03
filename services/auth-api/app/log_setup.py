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
"""

from __future__ import annotations

import logging
import sys

#: The loggers whose INFO lines are printed. `apg` is the parent of `apg.http`
#: and `apg.mcp`; the worker logs under its module's name (D1837).
LOGGERS = ("apg", "app.workflow_worker")

#: The marker on a handler this module installed. An attribute rather than a
#: type check, so a reload of this module still recognises its own handler.
MARKER = "_apg_stdout"


def configure_logging() -> None:
    """Attach one stdout handler at INFO to each logger in `LOGGERS`, once."""
    for name in LOGGERS:
        logger = logging.getLogger(name)
        if not any(getattr(handler, MARKER, False) for handler in logger.handlers):
            handler = logging.StreamHandler(sys.stdout)
            # The lines already begin with their own name (`apg.http.request {...}`).
            handler.setFormatter(logging.Formatter("%(message)s"))
            setattr(handler, MARKER, True)
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
