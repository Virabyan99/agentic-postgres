#!/usr/bin/env python
"""Session 2 edge probe — the deterministic HTTPS target.

This exists so that "Traefik routes this project, over a trusted certificate,
and returns *this* project's identity" is a measurable claim before any
application service exists. It is deliberately the smallest thing that can make
that claim falsifiable.

Standard library only. No dependency here would be hash-locked by
`requirements-dev.txt`, which covers the development environment rather than a
shipped image, so adding one would introduce an unlocked input into a container
that faces the public Internet.

What it must not do, and what the acceptance suite checks:

* log a request header, a query parameter, or a cookie — the access-log
  redaction policy is worthless if the origin logs what the edge dropped;
* read a secret, or mount one;
* return anything about the host, the container, or another project.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import FrameType

HEALTH_PATH = "/__apg/healthz"
SESSION = 2
LISTEN_PORT = 8080

#: Required. There is no default: a probe that cannot say which project it
#: belongs to cannot prove route isolation, and a wrong-but-plausible default
#: would make the isolation test pass for the wrong reason.
PROJECT_KEY = os.environ.get("PROJECT_KEY", "")


def log(**fields: object) -> None:
    """One structured line to stdout. Only the fields named here, ever."""
    print(json.dumps(fields, sort_keys=True, separators=(",", ":")), flush=True)


class Handler(BaseHTTPRequestHandler):
    # Never `HTTP/1.1` without correct framing; the base class handles 1.0
    # semantics safely and this server has no keep-alive requirement.
    protocol_version = "HTTP/1.0"
    server_version = "apg-edge-probe"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        started = time.monotonic()
        request_id = self.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Compared against the exact path. Traefik routes on Path(`/__apg/healthz`)
        # and an origin that also answered /__apg/healthz?x=1 or /__apg/healthz/
        # would make the route assertion weaker than it reads.
        if self.path == HEALTH_PATH:
            status, payload = 200, {
                "status": "ok",
                "project_key": PROJECT_KEY,
                "session": SESSION,
            }
        else:
            # No path echo, no container metadata, no server banner beyond the
            # fixed name above. An unknown route must reveal nothing.
            status, payload = 404, {"status": "not_found"}

        body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", request_id)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

        # `self.path` is logged only when it matched exactly, so a caller cannot
        # write attacker-controlled text into this project's logs.
        log(
            event="request",
            request_id=request_id,
            method="GET",
            path=HEALTH_PATH if status == 200 else "<unmatched>",
            status=status,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
        )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence the base class.

        Its default writes the raw request line to stderr, which would put the
        full path and query string into container logs — exactly what the
        access-log policy drops at the edge.
        """


def main() -> int:
    if not PROJECT_KEY:
        print("edge-probe: PROJECT_KEY is required", file=sys.stderr)
        return 2

    server = ThreadingHTTPServer(("", LISTEN_PORT), Handler)

    def stop(signum: int, frame: FrameType | None) -> None:
        del frame
        log(event="shutdown", signal=signum)
        server.shutdown()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    log(event="listening", port=LISTEN_PORT, project_key=PROJECT_KEY, session=SESSION)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
