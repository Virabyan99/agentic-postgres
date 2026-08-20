"""The agent plane's container-local health probe (ADR 0128).

**Run 4 wrote this module and removed it again** (D429). The transport guard as
it stood then forbade `urllib` anywhere under `services/auth-api/`, and weakening
a P0 guard to fit a liveness check was the wrong trade — so the probe waited for
the run that owns the health surface. ADR 0124 replaced that guard with a
per-module allowlist, and this module is its third row: a loopback HTTP request,
made by the container's own healthcheck, declared with its reason.

A module rather than a `python -c` one-liner in `compose.yaml`, because this
needs a `try`/`except` to tell the healthy answer from every other one, and a
one-liner that needs exception handling gets written as something that swallows
it. It is also then untestable, which for a check whose whole job is to fail
correctly is the wrong trade twice over.

**What it asks and why.** `/health/ready`, which reports only what startup
established — the key set and the capability lock are both loaded — and calls
nothing. This runtime holds no credential and opens no connection, so it has no
dependency of its own to probe, and a readiness answer that reached PostgREST
would take this container out of service for a fault that is not its own.

Neither health route is published. No Traefik router names them, so this probe
reaches them only because it runs *inside* the container.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request

#: Container-local, exactly as the auth service's health paths are (D231). The
#: public answer to "is this project up" stays `__apg/healthz`, served by
#: `edge-probe`, which already has a proof about it.
PROBE_URL = "http://127.0.0.1:8080/health/ready"

#: The only status that means healthy. `503` is the runtime's own answer when an
#: artefact is missing, and it must NOT pass -- a container serving with no
#: capability lock would answer every discovery with an empty list, which is
#: indistinguishable from a correctly-empty one.
EXPECTED_STATUS = 200

PROBE_TIMEOUT_SECONDS = 2

__all__ = ["EXPECTED_STATUS", "PROBE_TIMEOUT_SECONDS", "PROBE_URL", "main", "probe"]


def probe(url: str = PROBE_URL, *, timeout: float = PROBE_TIMEOUT_SECONDS) -> int:
    """The status the readiness route answers with.

    Returns the status rather than a verdict, so a test can assert what this saw
    as well as what it concluded -- and so the two are separable when a probe
    disagrees with a live container.

    **No `Origin` header**, and that is not incidental: the runtime refuses any
    request carrying one (ADR 0128), so a probe that sent one would fail against
    a perfectly healthy container.
    """
    request = urllib.request.Request(url, method="GET")  # noqa: S310 -- a fixed loopback URL
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as error:
        # `urlopen` raises on 4xx and 5xx, so the runtime's own 503 arrives here
        # rather than as a return value. Returning the code keeps `main`'s
        # comparison the only place a verdict is formed.
        return int(error.code)


def main() -> int:
    """Exit 0 only on the expected status.

    Every other outcome is exit 1, including a connection error: a process that
    cannot be reached is not ready, and reporting that as anything other than a
    failure is how a container stays in service while dead.

    Defined at module level, above `__main__`, because a `def` below the guard is
    not bound when it runs -- every import-based test passes and the deploy gets
    a `NameError` (D185).
    """
    try:
        status = probe()
    except OSError:
        return 1
    return 0 if status == EXPECTED_STATUS else 1


if __name__ == "__main__":  # pragma: no cover -- exercised as a subprocess
    sys.exit(main())
