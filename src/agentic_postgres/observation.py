"""Waiting for a fact to settle, without inventing one.

`bin/deploy-project.py` observes the certificate and the health route the
moment `compose up --wait` returns. Traefik's Docker provider polls, so a router
for a container that has only just started is not wired yet at that instant. The
first deployment of Project A recorded `tls: unavailable` and
`health: unavailable` for a route that answered `200` seconds later, and the
deployed document is the one artefact whose whole purpose is that its values
were measured rather than hoped for.

Retrying is not the same as assuming. The observation still runs, still reports
what it found, and still records `unavailable` when the deadline passes without
the fact settling. What changes is that a slow convergence is no longer written
down as a failure.

The clock and the sleep are injected so the tests exercise the real loop rather
than a stand-in for it, and do so without spending the timeout in wall time. A
reproduction that swaps out the thing under test is how a SIGPIPE bug in this
repository was "fixed" twice without being fixed once.
"""

from __future__ import annotations

import time
from collections.abc import Callable

#: Long enough for Traefik's provider poll plus an ACME order on a route that is
#: being seen for the first time; short enough that a genuinely broken
#: deployment is reported rather than waited on.
DEFAULT_TIMEOUT_SECONDS = 90.0

#: Polling interval. The observations shell out, so this is not a tight loop.
DEFAULT_INTERVAL_SECONDS = 3.0

__all__ = [
    "DEFAULT_INTERVAL_SECONDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "await_observation",
]


def await_observation[T](
    observe: Callable[[], T],
    is_settled: Callable[[T], bool],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    interval: float = DEFAULT_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> T:
    """Return the first settled observation, or the last unsettled one.

    ``observe`` is always called at least once, so a fact that is already true
    costs nothing. The value returned on timeout is a real observation, never a
    default: the caller records what was actually seen at the deadline.
    """
    if timeout < 0:
        raise ValueError("timeout must not be negative")
    if interval <= 0:
        raise ValueError("interval must be positive")

    deadline = now() + timeout
    while True:
        observed = observe()
        if is_settled(observed):
            return observed
        # Checked after observing, so the final observation is never discarded
        # for arriving a moment late.
        if now() >= deadline:
            return observed
        sleep(interval)
