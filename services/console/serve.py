"""The console: a fixed table of first-party files, our own headers, and no other verbs.

Session 43 (ADR 0280). The control project's own host serves the console beside
`/api/v1`, so the pages and the API share one origin -- which is what lets the
session be two `__Host-` cookies no script can read (ADR 0281). This process is
`services/docs/serve.py`'s shape, for the same reason ADR 0069 gave there:
**the Content-Security-Policy has to be ours.**

What it is not: a proxy, an authenticator or a file server. It never sees
`/api/...` (the edge routes that to the control project's `auth` container),
holds no credential, joins no request path to a directory, and answers a
closed table of paths. The pages call `/api/v1` from the browser; this process
only hands them over.

**The one value it serves that is not a file** is `/console/env.json`: the
API's public path, from `APG_CONSOLE_API_PATH` (compose interpolates the
rendered `CONTROL_ROUTE_PATH`, `identity.route_control_path`), so no page types
a path `naming.py` derives (ADR 0061).

**Since Session 44 (ADR 0285)** the policy names one more origin, the SQL
relay's (`connect-src 'self' wss://sql.<zone>`), from
`APG_CONSOLE_SQL_RELAY_ORIGIN` -- rendered by `naming.sql_relay_origin`, never
typed. It is read once at start and must be exactly `wss://<host>`: anything
else refuses to start, because a console whose policy admits the wrong origin
is a console that can send a database password there. `env.json` answers it
too, so the editor types no origin either.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import signal
import socketserver
import sys
from pathlib import Path
from typing import Any

PUBLIC = Path(os.environ.get("APG_CONSOLE_PUBLIC", "/app/public"))
PORT = int(os.environ.get("APG_CONSOLE_PORT", "8080"))
API_PATH = os.environ.get("APG_CONSOLE_API_PATH", "")

HTML = "text/html; charset=utf-8"
JAVASCRIPT = "text/javascript; charset=utf-8"
CSS = "text/css; charset=utf-8"
JSON = "application/json; charset=utf-8"
# Session 45 (ADR 0288): the two typefaces, their licences and the favicon.
FONT = "font/woff2"
TEXT = "text/plain; charset=utf-8"
SVG = "image/svg+xml"
FONTS_DIR = PUBLIC / "fonts"

#: Every file route this service has. A request for anything else is 404 before
#: a file system call is made. The console's views are a fragment router inside
#: `index.html` (`#/projects`, ...), so a reload of any view is `/console/`.
ROUTES: dict[str, tuple[Path, str]] = {
    "/console/": (PUBLIC / "index.html", HTML),
    "/accept": (PUBLIC / "accept.html", HTML),
    "/console/app.css": (PUBLIC / "app.css", CSS),
    "/console/app.js": (PUBLIC / "app.js", JAVASCRIPT),
    "/console/api.js": (PUBLIC / "api.js", JAVASCRIPT),
    "/console/scram.js": (PUBLIC / "scram.js", JAVASCRIPT),
    # Session 44 (ADR 0285): the SQL editor's wire client.
    "/console/pg.js": (PUBLIC / "pg.js", JAVASCRIPT),
    # Session 44 (ADR 0285, rig 44e): the editor's DOM-free decisions.
    "/console/sql.js": (PUBLIC / "sql.js", JAVASCRIPT),
    # Session 46 (ADR 0291): the creation's DOM-free decisions.
    "/console/create.js": (PUBLIC / "create.js", JAVASCRIPT),
    # Session 47 (ADR 0295 decision 3): the components, the shell, the
    # refusals' words, and a long operation's progress (DOM-free).
    "/console/ui.js": (PUBLIC / "ui.js", JAVASCRIPT),
    "/console/nav.js": (PUBLIC / "nav.js", JAVASCRIPT),
    "/console/messages.js": (PUBLIC / "messages.js", JAVASCRIPT),
    "/console/progress.js": (PUBLIC / "progress.js", JAVASCRIPT),
    # Session 47 Run 6 (D3017): what Connect and the editor hand a person to
    # copy -- a connection string, a snippet with its password, a result as
    # CSV -- DOM-free.
    "/console/copies.js": (PUBLIC / "copies.js", JAVASCRIPT),
    "/console/pages.json": (PUBLIC / "pages.json", JSON),
    # Session 45 (ADR 0288): one copy of the shared assets, which the site's
    # builder copies (D2814) -- the files rig 45a made, pinned by sha256.
    "/console/fonts/schibsted-grotesk.woff2": (FONTS_DIR / "schibsted-grotesk.woff2", FONT),
    "/console/fonts/jetbrains-mono.woff2": (FONTS_DIR / "jetbrains-mono.woff2", FONT),
    "/console/fonts/OFL-schibsted-grotesk.txt": (FONTS_DIR / "OFL-schibsted-grotesk.txt", TEXT),
    "/console/fonts/OFL-jetbrains-mono.txt": (FONTS_DIR / "OFL-jetbrains-mono.txt", TEXT),
    "/console/favicon.svg": (PUBLIC / "favicon.svg", SVG),
}

#: Where the API's public path is served, and the only answer not read from a file.
ENV_PATH = "/console/env.json"

#: Absolute, unlike the docs page's: the console owns its host's root, and the
#: edge strips nothing in front of it.
REDIRECTS: dict[str, str] = {
    "/": "/console/",
    "/console": "/console/",
}

HEALTH_PATH = "/__apg/healthz"

#: ADR 0280's directives. `default-src 'none'` first, so anything not named is
#: refused; no `'unsafe-inline'` anywhere, because every script and stylesheet is
#: one of the files above; `img-src data:` only for the factor's QR (ADR 0282);
#: `connect-src` keeps every fetch on this origin and, since ADR 0285, names the
#: SQL relay's origin and nothing else; `form-action 'none'` because no page
#: submits a form -- `api.js` sends JSON, the editor intercepts its own;
#: `font-src 'self'` since ADR 0288, for the two typefaces above and no host.
DIRECTIVES = (
    "default-src 'none'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "connect-src 'self' {relay}",
    "font-src 'self'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
)

#: `wss://<host>` and nothing else: no path, no port, no wildcard, no `ws:`.
RELAY_ORIGIN_SHAPE = re.compile(
    r"wss://(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


def policy(relay_origin: str) -> str:
    """ADR 0280's policy with the relay's origin in `connect-src` (ADR 0285)."""
    if not RELAY_ORIGIN_SHAPE.fullmatch(relay_origin) or len(relay_origin) > 259:
        raise ValueError("the relay's origin is not exactly wss://<host>")
    return "; ".join(DIRECTIVES).format(relay=relay_origin)


def security_headers(relay_origin: str) -> dict[str, str]:
    """Every header every answer carries, for one relay origin."""
    return {
        "Content-Security-Policy": policy(relay_origin),
        # The accept page's link carries the token in its fragment, which no
        # browser sends anyway; `no-referrer` is the second lock (ADR 0282).
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Cache-Control": "no-store",
    }


#: Read once at start. An origin that is not `wss://<host>` leaves the policy
#: unbuilt and `main` refuses to start; nothing is ever served without it.
RELAY_ORIGIN = os.environ.get("APG_CONSOLE_SQL_RELAY_ORIGIN", "")
try:
    SECURITY_HEADERS: dict[str, str] = security_headers(RELAY_ORIGIN)
    CONTENT_SECURITY_POLICY = SECURITY_HEADERS["Content-Security-Policy"]
    REFUSED = ""
except ValueError as refused:
    SECURITY_HEADERS = {}
    CONTENT_SECURITY_POLICY = ""
    REFUSED = f"APG_CONSOLE_SQL_RELAY_ORIGIN: {refused}"


class Handler(http.server.BaseHTTPRequestHandler):
    """GET and HEAD, the table above, nothing else."""

    server_version = "apg-console"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def end_headers(self) -> None:
        """Every answer carries the policy -- a 404, a redirect, and the base
        handler's own 501 for any other verb included."""
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        """One line per request, to stdout, naming no header and no query --
        a cookie or a fragment never reaches a log line here (D2678)."""
        path = (getattr(self, "path", None) or "").split("?", 1)[0]
        status = args[1] if len(args) > 1 else ""
        sys.stdout.write(f"apg-console {getattr(self, 'command', None)} {path} {status}\n")

    def _respond(self, status: int, body: bytes, content_type: str, *, head: bool) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _redirect(self, target: str, *, head: bool) -> None:
        body = b"moved\n"
        self.send_response(301)
        self.send_header("Location", target)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _serve(self, *, head: bool) -> None:
        # The query string is discarded rather than parsed: no route takes one.
        path = self.path.split("?", 1)[0]

        if path == HEALTH_PATH:
            self._respond(200, b'{"status":"ok"}', JSON, head=head)
            return

        target = REDIRECTS.get(path)
        if target is not None:
            self._redirect(target, head=head)
            return

        if path == ENV_PATH:
            if not API_PATH:
                self._respond(503, b"not configured\n", "text/plain; charset=utf-8", head=head)
                return
            answer = {"api": API_PATH, "sql_relay": RELAY_ORIGIN}
            body = (json.dumps(answer, sort_keys=True) + "\n").encode("utf-8")
            self._respond(200, body, JSON, head=head)
            return

        route = ROUTES.get(path)
        if route is None:
            self._respond(404, b"not found\n", "text/plain; charset=utf-8", head=head)
            return

        source, content_type = route
        try:
            body = source.read_bytes()
        except OSError:
            self._respond(503, b"unavailable\n", "text/plain; charset=utf-8", head=head)
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
    if REFUSED:
        sys.stderr.write(f"apg-console refused to start: {REFUSED}\n")
        return 2
    server = Server(("0.0.0.0", PORT), Handler)  # noqa: S104

    def shut_down(signum: int, frame: object) -> None:
        server.shutdown()

    signal.signal(signal.SIGTERM, shut_down)
    signal.signal(signal.SIGINT, shut_down)

    sys.stdout.write(f"apg-console listening on {PORT}\n")
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
