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

**Two surfaces, one process** (D226, ADR 0087). ``/rest`` is the REST API's
reference and ``/app`` is the application API's. The edge strips the
documentation root before either reaches here, so what arrives is ``/rest/``
or ``/app/`` and not the published ``/docs/rest/`` -- and the container never
learns the published prefix, which is what keeps `naming.py` the one authority
for it (ADR 0061).

**The slash-less form is redirected, and that is a fix rather than a nicety.**
The pages reference their assets relatively, so a browser given ``/docs/rest``
resolves ``standalone.js`` against ``/docs/`` and asks for
``/docs/standalone.js`` -- measured, **404**, with ``/docs/rest/standalone.js``
at 200 as the control. The page returned 200, the HTML was correct, and it did
not render. Until ADR 0087 this process could not have repaired it: the strip
removed the whole page path, so ``/docs/rest`` and ``/docs/rest/`` both arrived
as ``/`` and the difference was gone before any code here ran.

The `Location` is **relative** -- ``rest/`` from ``/rest`` -- because this
process does not know the published prefix and must not be told it.

What this deliberately is not: a general static file server. It serves a fixed
table of paths. There is no path joining, no directory walk, no content
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
APP_SNAPSHOT = Path(os.environ.get("APG_DOCS_APP_SNAPSHOT", "/app/snapshot/app-openapi.json"))
PORT = int(os.environ.get("APG_DOCS_PORT", "8080"))

HTML = "text/html; charset=utf-8"
JAVASCRIPT = "text/javascript; charset=utf-8"
JSON = "application/json; charset=utf-8"

#: The two surfaces, and the segment each is served under once the edge has
#: removed the documentation root. The names are the ones `naming.py` derives
#: -- `DOCS_PAGE_PATH` is `/docs/rest` and `DOCS_APP_PAGE_PATH` is `/docs/app`
#: -- but only the last segment reaches here, and nothing in this process may
#: reconstruct the rest of it.
REST_SEGMENT = "/rest"
APP_SEGMENT = "/app"

#: Every route this service has. A request for anything else is 404 before a
#: file system call is made.
#:
#: One `standalone.js` under two paths, deliberately: it is the same vendored
#: bundle, and serving it twice from one file is what makes "one image, one CSP"
#: true rather than merely claimed. The two documents differ, and so do the two
#: HTML pages -- `index.html` carries ADR 0060's note about verbs the REST
#: surface advertises and refuses, which is not true of the application API and
#: must not appear over it.
ROUTES: dict[str, tuple[Path, str]] = {
    f"{REST_SEGMENT}/": (PUBLIC / "index.html", HTML),
    f"{REST_SEGMENT}/index.html": (PUBLIC / "index.html", HTML),
    f"{REST_SEGMENT}/standalone.js": (PUBLIC / "standalone.js", JAVASCRIPT),
    f"{REST_SEGMENT}/openapi.json": (SNAPSHOT, JSON),
    f"{APP_SEGMENT}/": (PUBLIC / "app.html", HTML),
    f"{APP_SEGMENT}/index.html": (PUBLIC / "app.html", HTML),
    f"{APP_SEGMENT}/standalone.js": (PUBLIC / "standalone.js", JAVASCRIPT),
    f"{APP_SEGMENT}/openapi.json": (APP_SNAPSHOT, JSON),
}

#: The slash-less form of each surface, and the relative target it redirects to.
#: Relative, so the answer is correct whatever prefix the edge published this
#: page under -- an absolute `/rest/` would be a second derivation of a path
#: this process is deliberately not told (ADR 0061).
REDIRECTS: dict[str, str] = {
    REST_SEGMENT: f"{REST_SEGMENT.lstrip('/')}/",
    APP_SEGMENT: f"{APP_SEGMENT.lstrip('/')}/",
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

    def _redirect(self, target: str, *, head: bool) -> None:
        """301 to the with-slash form, with a relative `Location`.

        Permanent rather than temporary: the slash-less form is never the right
        address for this page and never will be, so a client that remembers the
        answer is remembering something true.

        The body is the same short text every other answer here uses, and it
        carries the same security headers -- a redirect is a response, and a
        response without the CSP is a response that opted out of it.
        """
        self.send_response(301)
        self.send_header("Location", target)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        body = b"moved\n"
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
            self._respond(200, b'{"status":"ok"}', JSON, head=head)
            return

        target = REDIRECTS.get(path)
        if target is not None:
            self._redirect(target, head=head)
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
