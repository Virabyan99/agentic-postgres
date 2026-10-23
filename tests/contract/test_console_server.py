"""The console's server: a closed route table, the policy on every answer, no query logged.

Session 43 (ADR 0280): `CON-SERVE-001`. `services/console/serve.py` imported
and SERVED -- a real `ThreadingTCPServer` on a free loopback port in this
process, asked over HTTP -- because what matters is what a browser receives,
not what the module's constants say. `test_docs_service.py` holds the docs
server structurally; this one asks the console.
"""

from __future__ import annotations

import http.client
import importlib.util
import io
import os
import re
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

SERVICE = REPO_ROOT / "services" / "console"
PUBLIC = SERVICE / "public"

#: ADR 0280's policy, written out here so the module's policy is compared
#: with the decision rather than with itself -- and ADR 0285's, which is the
#: same string with ONE more origin in `connect-src`, for the fixture's relay.
#: Both carry `font-src 'self'` since ADR 0288 (D2813 (c)), nothing else moved.
ADR_0280_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
RELAY_ORIGIN = "wss://sql.example.test"
POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self' wss://sql.example.test; font-src 'self'; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'"
)
#: ADR 0288 (D2813 (d)): the typefaces, their licences and the favicon.
FONTS = {
    "/console/fonts/schibsted-grotesk.woff2": "fonts/schibsted-grotesk.woff2",
    "/console/fonts/jetbrains-mono.woff2": "fonts/jetbrains-mono.woff2",
}
LISTED = (
    "/console/",
    "/accept",
    "/console/app.css",
    "/console/app.js",
    "/console/api.js",
    "/console/scram.js",
    "/console/pg.js",
    "/console/sql.js",
    "/console/pages.json",
    "/console/fonts/schibsted-grotesk.woff2",
    "/console/fonts/jetbrains-mono.woff2",
    "/console/fonts/OFL-schibsted-grotesk.txt",
    "/console/fonts/OFL-jetbrains-mono.txt",
    "/console/favicon.svg",
)


@pytest.fixture(scope="module")
def serve(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    """The module, loaded with this checkout's `public/` and an API path, as
    compose gives the container `APG_CONSOLE_API_PATH`."""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("APG_CONSOLE_PUBLIC", str(PUBLIC))
    monkeypatch.setenv("APG_CONSOLE_API_PATH", "/api/v1")
    monkeypatch.setenv("APG_CONSOLE_SQL_RELAY_ORIGIN", RELAY_ORIGIN)
    specification = importlib.util.spec_from_file_location(
        "apg_console_serve", SERVICE / "serve.py"
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    monkeypatch.undo()
    yield module


@pytest.fixture(scope="module")
def port(serve: Any) -> Iterator[int]:
    server = serve.Server(("127.0.0.1", 0), serve.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def _ask(port: int, method: str, path: str) -> http.client.HTTPResponse:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request(method, path)
    response = connection.getresponse()
    response.read()
    connection.close()
    return response


def test_only_the_listed_paths_answer(serve: Any, port: int) -> None:
    """A closed table: the listed files, the API path, two redirects and the
    health path -- and nothing a path could name besides."""
    assert tuple(serve.ROUTES) == LISTED
    assert serve.REDIRECTS == {"/": "/console/", "/console": "/console/"}
    for path in LISTED:
        assert _ask(port, "GET", path).status == 200, path
    assert _ask(port, "GET", "/console/env.json").status == 200
    for path in ("/console/../serve.py", "/serve.py", "/app/serve.py", "/console/x",
                 "/console/public/app.js", "/etc/passwd", "/console/index.html",
                 "/api/v1/me", "/docs/rest/"):  # fmt: skip
        assert _ask(port, "GET", path).status == 404, path
    moved = _ask(port, "GET", "/")
    assert (moved.status, moved.getheader("Location")) == (301, "/console/")


def test_every_answer_carries_the_policy(serve: Any, port: int) -> None:
    """The policy on a 200, a 301, a 404, a HEAD and the base handler's 501 --
    a response without it would be a response that opted out of it."""
    assert serve.CONTENT_SECURITY_POLICY == POLICY
    assert "unsafe" not in POLICY
    answers = [
        _ask(port, "GET", "/console/"),
        _ask(port, "HEAD", "/accept"),
        _ask(port, "GET", "/"),
        _ask(port, "GET", "/missing"),
        _ask(port, "POST", "/console/"),
    ]
    assert [answer.status for answer in answers] == [200, 200, 301, 404, 501]
    for answer in answers:
        assert answer.getheader("Content-Security-Policy") == POLICY, answer.status
        assert answer.getheader("Referrer-Policy") == "no-referrer", answer.status
        assert answer.getheader("X-Content-Type-Options") == "nosniff", answer.status
        assert answer.getheader("X-Frame-Options") == "DENY", answer.status
        assert answer.getheader("Cross-Origin-Opener-Policy") == "same-origin", answer.status
        assert answer.getheader("Cache-Control") == "no-store", answer.status


def test_the_env_answer_is_the_api_path(port: int) -> None:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", "/console/env.json")
    answer = connection.getresponse()
    assert answer.read() == b'{"api": "/api/v1", "sql_relay": "wss://sql.example.test"}\n'
    assert answer.getheader("Content-Type") == "application/json; charset=utf-8"
    connection.close()


def test_the_log_names_no_query(serve: Any) -> None:
    """A link's fragment never reaches a server, and a query or a header that
    did must not reach the log line either (D2678)."""
    handler = serve.Handler.__new__(serve.Handler)
    handler.command = "GET"
    handler.path = "/console/?token=planted-value"
    out = io.StringIO()
    with redirect_stdout(out):
        handler.log_message('"%s" %s %s', "GET /console/?token=planted-value HTTP/1.1", "200", "-")
    assert out.getvalue() == "apg-console GET /console/ 200\n"


def _assets(page: Path) -> list[str]:
    text = page.read_text(encoding="utf-8")
    return re.findall(r'<(?:script|link|img)\b[^>]*?\b(?:src|href)="([^"]+)"', text)


def test_every_asset_is_our_own_file(serve: Any) -> None:
    """Every `<script src>`, `<link href>` and `<img src>` in the two pages, and
    every module a script imports, is one of the server's own routes -- nothing
    from another origin, nothing the table does not serve."""
    for page in (PUBLIC / "index.html", PUBLIC / "accept.html"):
        assets = _assets(page)
        assert assets, f"{page.name} names no asset: the check would read nothing"
        for asset in assets:
            assert asset in serve.ROUTES, f"{page.name} loads {asset!r}"
        assert "<script>" not in page.read_text(encoding="utf-8"), (
            f"{page.name} has an inline script"
        )
    imports = re.compile(r'^import\b[^;]*?\bfrom\s+"([^"]+)";', re.MULTILINE)
    found = 0
    for script in PUBLIC.glob("*.js"):
        text = script.read_text(encoding="utf-8")
        assert "import(" not in text, f"{script.name} imports dynamically"
        for imported in imports.findall(text):
            found += 1
            assert imported in serve.ROUTES, f"{script.name} imports {imported!r}"
    assert found >= 2, "no import statement was read: the check would read nothing"


def test_no_method_but_get_and_head(serve: Any, port: int) -> None:
    verbs = {name for name in dir(serve.Handler) if name.startswith("do_")}
    assert verbs == {"do_GET", "do_HEAD"}
    for method in ("POST", "PUT", "DELETE", "OPTIONS"):
        assert _ask(port, method, "/console/").status == 501, method


def test_the_image_bakes_only_its_own_files() -> None:
    """One stage from the lock's base, the public files and the server, a
    non-root user, no default for the base (ADR 0077)."""
    text = (SERVICE / "Dockerfile").read_text(encoding="utf-8")
    assert re.findall(r"^FROM .*$", text, flags=re.MULTILINE) == ["FROM ${PYTHON_BASE_IMAGE}"]
    assert "ARG PYTHON_BASE_IMAGE\n" in text
    assert re.findall(r"^COPY .*$", text, flags=re.MULTILINE) == [
        "COPY public /app/public",
        "COPY serve.py /app/serve.py",
    ]
    assert "USER 65532:65532" in text
    # Every file under `public/`, at any depth, by its RELATIVE path, is a
    # routed file and nothing else is there (ADR 0288, D2813 (e): stricter than
    # the top-level names it compared before -- a stray file in `fonts/` fails).
    baked = sorted(path.relative_to(PUBLIC).as_posix() for path in PUBLIC.rglob("*")
                   if path.is_file())  # fmt: skip
    assert baked == sorted(path.as_posix() for path, _ in serve_routes_files())
    assert sorted(path.relative_to(PUBLIC).as_posix() for path in PUBLIC.rglob("*")
                  if path.is_dir()) == ["fonts"]  # fmt: skip


def serve_routes_files() -> list[tuple[Path, str]]:
    """The files the table serves, relative to `public/` -- and nothing else is there."""
    specification = importlib.util.spec_from_file_location(
        "apg_console_files", SERVICE / "serve.py"
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return [
        (path.relative_to(module.PUBLIC), kind)
        for path, kind in dict.fromkeys(module.ROUTES.values())
    ]


def test_the_fonts_are_served_as_fonts(serve: Any, port: int) -> None:
    """ADR 0288: each typeface answers 200 as `font/woff2` with the policy and
    `nosniff`, its bytes the committed file's; each licence is plain text and
    the favicon an SVG -- all from this origin, so `font-src 'self'` admits them."""
    for route, relative in FONTS.items():
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        connection.request("GET", route)
        answer = connection.getresponse()
        body = answer.read()
        connection.close()
        assert answer.status == 200, route
        assert answer.getheader("Content-Type") == "font/woff2", route
        assert answer.getheader("Content-Security-Policy") == POLICY, route
        assert answer.getheader("X-Content-Type-Options") == "nosniff", route
        assert body == (PUBLIC / relative).read_bytes() and body[:4] == b"wOF2", route
    kinds = {route: kind for route, (_, kind) in serve.ROUTES.items()}
    assert kinds["/console/fonts/OFL-schibsted-grotesk.txt"] == "text/plain; charset=utf-8"
    assert kinds["/console/fonts/OFL-jetbrains-mono.txt"] == "text/plain; charset=utf-8"
    assert kinds["/console/favicon.svg"] == "image/svg+xml"
    for route in LISTED:
        if route.startswith("/console/fonts/") or route == "/console/favicon.svg":
            assert _ask(port, "GET", route).status == 200, route


def test_the_policy_admits_the_relay_alone(serve: Any) -> None:
    """ADR 0285: every directive of ADR 0280's policy byte for byte, except that
    `connect-src` gains the relay's origin -- one origin, and nothing else moved."""
    assert serve.CONTENT_SECURITY_POLICY == POLICY == serve.policy(RELAY_ORIGIN)
    before = ADR_0280_POLICY.split("; ")
    after = POLICY.split("; ")
    assert len(before) == len(after)
    changed = [(old, new) for old, new in zip(before, after, strict=True) if old != new]
    assert changed == [("connect-src 'self'", f"connect-src 'self' {RELAY_ORIGIN}")]
    assert serve.policy("wss://sql.agenticpostgresql.com").count("wss://") == 1


@pytest.mark.parametrize(
    "origin",
    ["", "ws://sql.example.test", "wss://*", "wss://*.example.test", "wss://sql.example.test/",
     "wss://sql.example.test/path", "wss://sql.example.test:443", "https://sql.example.test",
     "wss://SQL.example.test", "wss://sql.example.test wss://evil.test", "wss://localhost"],
)  # fmt: skip
def test_a_bad_relay_origin_refuses_to_start(serve: Any, origin: str) -> None:
    """Anything but exactly `wss://<host>` builds no policy, and the server, as
    the image runs it, exits before it listens."""
    with pytest.raises(ValueError, match="wss://<host>"):
        serve.policy(origin)
    environment = {
        **{k: v for k, v in os.environ.items() if not k.startswith("APG_CONSOLE_")},
        "APG_CONSOLE_PUBLIC": str(PUBLIC),
        "APG_CONSOLE_PORT": "0",
        "APG_CONSOLE_API_PATH": "/api/v1",
        "APG_CONSOLE_SQL_RELAY_ORIGIN": origin,
    }
    started = subprocess.run(
        [sys.executable, str(SERVICE / "serve.py")], env=environment, capture_output=True,
        text=True, timeout=30, check=False,
    )  # fmt: skip
    assert started.returncode == 2
    assert started.stdout == ""
    assert started.stderr.startswith("apg-console refused to start: APG_CONSOLE_SQL_RELAY_ORIGIN")
