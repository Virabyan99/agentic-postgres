"""The documentation service: four files, fixed headers, and no other verbs.

The server is first-party for one reason, and it is the reason ADR 0069 chose a
build over an upstream image: **the Content-Security-Policy has to be ours.**

The Scalar bundle is not self-contained and no version of it is. Measured on
1.36.2 and 1.64.1, ``dist/browser/standalone.js`` names ``fonts.scalar.com``
fourteen times and ``proxy.scalar.com`` beside it, and ``withDefaultFonts`` is
declared ``default: true`` (D202). ``index.html`` turns both off, and that is a
promise about a third party's code honouring its own flag. The CSP below is a
rule the visitor's browser enforces against whatever the bundle attempts, and it
is the only place in this design where "loads nothing from the internet" stops
depending on somebody else's default.

What this deliberately is not: a general static file server. It serves four
paths from a table. There is no path joining, no directory walk, no content
negotiation and no way to name a file that is not listed -- which is a shorter
argument than any traversal defence, because there is no path to traverse.
"""

from __future__ import annotations

import http.server
import os
import signal
import socketserver
import sys
from pathlib import Path
from typing import Any

PUBLIC = Path("/app/public")
SNAPSHOT = Path(os.environ.get("APG_DOCS_SNAPSHOT", "/app/snapshot/openapi.json"))
PORT = int(os.environ.get("APG_DOCS_PORT", "8080"))

#: Every route this service has. A request for anything else is 404 before a
#: file system call is made.
ROUTES: dict[str, tuple[Path, str]] = {
    "/": (PUBLIC / "index.html", "text/html; charset=utf-8"),
    "/index.html": (PUBLIC / "index.html", "text/html; charset=utf-8"),
    "/standalone.js": (PUBLIC / "standalone.js", "text/javascript; charset=utf-8"),
    "/openapi.json": (SNAPSHOT, "application/json; charset=utf-8"),
}

HEALTH_PATH = "/__apg/healthz"

#: `default-src 'none'` first, so anything not named below is refused rather
#: than inherited. `script-src 'self'` is what stops the bundle reaching
#: `proxy.scalar.com`; `font-src 'self'` is what stops it reaching
#: `fonts.scalar.com` even if `withDefaultFonts` were ever to regress;
#: `connect-src 'self'` is what keeps the document fetch on this origin.
#:
#: `style-src` carries `'unsafe-inline'` and that is a real concession, made
#: knowingly: Scalar writes component styles into the document at runtime, and
#: without it the page renders unstyled. It is bounded by `default-src 'none'`
#: -- an inline *style* cannot fetch, navigate or execute -- and by `script-src`
#: carrying no such allowance, which is where the risk would actually live.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "font-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    )
)

SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    # The page is public and carries no identity. Saying so explicitly keeps a
    # future caching layer from having to guess.
    "Cache-Control": "no-store",
}


class Handler(http.server.BaseHTTPRequestHandler):
    """GET and HEAD, four paths, nothing else."""

    server_version = "apg-docs"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        """One line per request, to stdout, naming no header and no query.

        The default writes to stderr and includes the raw request line. This
        page carries no credential by design, and a log that records what a
        caller sent is a place one could arrive anyway.
        """
        sys.stdout.write(f"apg-docs {self.command} {self.path.split('?', 1)[0]} {args[1]}\n")

    def _respond(self, status: int, body: bytes, content_type: str, *, head: bool) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _serve(self, *, head: bool) -> None:
        # The query string is discarded rather than parsed: no route takes one,
        # and a route table lookup on the raw path would miss `/?x=1`.
        path = self.path.split("?", 1)[0]

        if path == HEALTH_PATH:
            self._respond(200, b'{"status":"ok"}', "application/json; charset=utf-8", head=head)
            return

        route = ROUTES.get(path)
        if route is None:
            self._respond(404, b"not found\n", "text/plain; charset=utf-8", head=head)
            return

        source, content_type = route
        try:
            body = source.read_bytes()
        except OSError:
            # The snapshot is a mount, so "absent" is a deployment state rather
            # than an impossibility -- and it must not read as an empty
            # document, which is a valid OpenAPI file describing nothing.
            self._respond(503, b"document unavailable\n", "text/plain; charset=utf-8", head=head)
            return

        self._respond(200, body, content_type, head=head)

    def do_GET(self) -> None:
        self._serve(head=False)

    def do_HEAD(self) -> None:
        self._serve(head=True)


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    server = Server(("0.0.0.0", PORT), Handler)  # noqa: S104

    def shut_down(signum: int, frame: object) -> None:
        server.shutdown()

    signal.signal(signal.SIGTERM, shut_down)
    signal.signal(signal.SIGINT, shut_down)

    sys.stdout.write(f"apg-docs listening on {PORT}, snapshot {SNAPSHOT}\n")
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
