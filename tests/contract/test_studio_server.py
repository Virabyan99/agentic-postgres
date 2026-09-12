"""`STU-BIND-001`'s seven proofs, against the real server (Session 24 Run 3).

Studio is launched as a subprocess -- the product's own command (D1114) -- and
driven the way the page drives it, with `http.client`. What it is pointed at is
a **stand-in for an HTTP SHAPE, not for the product**, and that distinction is
the module's whole licence to exist: these proofs are about the server's own
rules, which have nothing to do with what a deployment answers, and arranging a
real deployment to ask them would cost three minutes per assertion.

**The stand-in proves nothing about a deployment and is not allowed to.**
`test_studio_runtime.py` is where every positive path is proved -- against
`apg dev`, the real auth application, real PostgREST and the real edge. If a
proof here and a proof there ever disagree, the one with the product in it is
right.

**Marked, and the marks are load-bearing** (D1240).
"""

from __future__ import annotations

import ast
import http.client
import json
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, studio

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

STUDIO = REPO_ROOT / "bin" / "studio.sh"
PROJECT = REPO_ROOT / "project.example.yaml"
SNAPSHOT = REPO_ROOT / "projects" / "example" / "contracts" / "postgrest-openapi.canonical.json"
REST_PATH = "/api/rest"

#: A token the stand-in hands out. Distinctive so a scan for it over stderr and
#: over every page response means something (D105).
FAKE_TOKEN = "stand-in-access-token-a7f3e19c4b2d"  # noqa: S105
FAKE_REFRESH = "stand-in-refresh-token-51ce9042"
#: What the stand-in puts in a REFUSED body, to prove it does not travel (D433).
REFUSAL_BODY = "upstream-prose-that-must-not-reach-the-page"
#: An environment variable shaped like a credential, for the arm that proves
#: nothing reads one. A dict rather than a keyword so the value is data.
PASSWORD_SHAPED_VARIABLE = {"APG_STUDIO_PASSWORD": "a-correct-horse-battery-staple"}


class StandIn:
    """One loopback server answering the shapes `bin/studio.py` calls.

    Not a mock of the auth service: it answers the STATUS and the SHAPE, and
    every field it invents is one this module then asserts does NOT reach the
    page. `answers` is mutable so an arm can make one endpoint refuse without
    standing a second server up.
    """

    def __init__(self) -> None:
        self.answers: dict[str, tuple[int, Any]] = {}
        self.requests: list[tuple[str, str]] = []
        self.server: ThreadingHTTPServer | None = None
        self.port = 0

    def document(self) -> dict[str, Any]:
        """The committed snapshot, re-addressed to this server.

        `schemes` stays `["https"]` even though the transport is cleartext
        loopback: `openapi_normalize` refuses `["http"]` outright (D1261), and
        the field describes the address a caller was told to use rather than the
        socket this rig happens to be on. The host is this server's, so
        `published_address` derives it from the route and the two agree.
        """
        document = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        document["host"] = f"127.0.0.1:{self.port}"
        document["basePath"] = REST_PATH
        document["schemes"] = ["https"]
        return document

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "apg-studio-standin"
            sys_version = ""

            def log_message(self, format: str, *args: Any) -> None:
                return

            def respond(self, status: int, payload: Any, kind: str = "application/json") -> None:
                body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def route(self) -> None:
                path = self.path.split("?", 1)[0]
                outer.requests.append((self.command, path))
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)

                if path in outer.answers:
                    status, payload = outer.answers[path]
                    self.respond(status, payload)
                    return
                if path == f"{REST_PATH}/":
                    self.respond(200, outer.document())
                    return
                if path == "/auth/login":
                    self.respond(
                        200,
                        {
                            "access_token": FAKE_TOKEN,
                            "token_type": "Bearer",
                            "expires_at": int(time.time()) + 900,
                            "token_use": "access",
                            "refresh_token": FAKE_REFRESH,
                        },
                    )
                    return
                if path == "/auth/sessions":
                    self.respond(200, [])
                    return
                if path == "/auth/me":
                    self.respond(200, {"username": "ada", "scopes": []})
                    return
                if path in ("/admin/agents", "/admin/audit"):
                    self.respond(200, {"audit": [], "limit": 500} if "audit" in path else [])
                    return
                self.respond(404, {"status": "not_found"})

            do_GET = do_POST = do_PATCH = do_DELETE = route

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def deployed(self) -> dict[str, Any]:
        return {
            "document_kind": "deployed",
            "routes": {
                "rest": {"status": "ready", "url": f"{self.base}{REST_PATH}"},
                "app": {"status": "ready", "url": self.base},
            },
        }


class Launched:
    """A running `apg studio`, its URL, its key and its stderr."""

    def __init__(self, process: subprocess.Popen[str], url: str, lines: list[str]) -> None:
        self.process = process
        self.url = url
        self.lines = lines
        self.port = int(url.split("/open/")[0].rsplit(":", 1)[1])
        self.key = url.rsplit("/open/", 1)[1]
        self.bound = f"127.0.0.1:{self.port}"

    def call(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        cookie: bool = True,
        custom: bool = True,
    ) -> tuple[int, dict[str, str], bytes]:
        """One request, the way the page makes it unless an arm says otherwise."""
        sent = {"Host": self.bound}
        if cookie:
            sent["Cookie"] = f"{studio.LAUNCH_COOKIE}={self.key}"
        if custom:
            sent[studio.CUSTOM_HEADER] = "1"
        sent.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=sent)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()


def launch(tmp_path: Path, stand_in: StandIn) -> Launched:
    """`bin/studio.sh`, as a subprocess, with a `0600` password file."""
    document = tmp_path / "outputs.json"
    document.write_text(json.dumps(stand_in.deployed()), encoding="utf-8")
    password = tmp_path / f"password-{secrets.token_hex(4)}"
    password.write_text("a-correct-horse-battery-staple\n", encoding="utf-8")
    password.chmod(0o600)

    process = subprocess.Popen(
        [
            str(STUDIO), "--project", str(PROJECT), "--outputs", str(document),
            "--username", "ada", "--password-file", str(password),
        ],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )  # fmt: skip

    deadline = time.monotonic() + 60
    url = ""
    lines: list[str] = []
    while time.monotonic() < deadline:
        line = process.stdout.readline() if process.stdout else ""
        if not line:
            if process.poll() is not None:
                break
            continue
        lines.append(line.rstrip("\n"))
        if "open http://" in line:
            url = line.split("open ", 1)[1].strip()
            break
    if not url:
        process.kill()
        stderr = process.stderr.read() if process.stderr else ""
        pytest.fail(f"studio printed no URL. stdout={lines} stderr={stderr[:800]}")
    return Launched(process, url, lines)


@pytest.fixture
def running(tmp_path: Path) -> Any:
    stand_in = StandIn()
    stand_in.start()
    started = None
    try:
        started = launch(tmp_path, stand_in)
        yield started, stand_in
    finally:
        if started is not None:
            started.process.terminate()
            try:
                started.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                started.process.kill()
            if started.process.stderr:
                started.lines.append(started.process.stderr.read())
        stand_in.stop()


# ---------------------------------------------------------------------------
# STU-BIND-001
# ---------------------------------------------------------------------------


def test_the_listener_is_on_loopback_and_nowhere_else(running: Any) -> None:
    """Measured two ways, because one of them may not be available.

    `ss -ltn` is the reading rig 24a took: the bound socket shows
    `127.0.0.1:PORT` and not `0.0.0.0:PORT`. Where `ss` is absent the same
    question is asked with a socket -- connecting to this host's own INTERFACE
    address, which is refused for a loopback listener and accepted for one bound
    to `0.0.0.0`.

    **The interface address is read from the interface.** Rig 24a measured
    `socket.gethostbyname_ex(gethostname())` returning `['127.0.1.1']` on this
    machine, which is no use for the question: an arm that used it would connect
    to loopback under another name and report a pass for a server bound
    anywhere.
    """
    started, _ = running
    asked = False

    if shutil.which("ss"):
        listing = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, check=False).stdout
        rows = [line for line in listing.splitlines() if f":{started.port}" in line]
        assert rows, f"ss lists no listener on {started.port}: {listing}"
        assert all("127.0.0.1:" in row for row in rows), (
            f"the studio socket is not loopback-only: {rows}"
        )
        assert not any("0.0.0.0:" in row.split()[3] for row in rows), rows
        asked = True

    interface = ""
    if shutil.which("hostname"):
        for candidate in subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, check=False
        ).stdout.split():
            if ":" not in candidate and not candidate.startswith("127."):
                interface = candidate
                break
    if interface:
        with socket.socket() as probe:
            probe.settimeout(3)
            with pytest.raises(OSError):
                probe.connect((interface, started.port))
        asked = True

    assert asked, (
        "neither `ss` nor an interface address was available, so this test asked nothing. "
        "It must not pass by being unable to look"
    )
    # The control that the port is a port at all.
    with socket.socket() as probe:
        probe.settimeout(3)
        probe.connect(("127.0.0.1", started.port))


def test_there_is_no_bind_flag_and_the_address_is_a_constant() -> None:
    """No switch turns the decision off (D1245, D694).

    Asserted over the SOURCE of both files: a flag would have to be declared to
    exist, and `127.0.0.1` appears exactly where the constant is defined and is
    passed to the server from there. A test that read `studio.BIND_ADDRESS` and
    compared it to `"127.0.0.1"` would be comparing a constant to itself.
    """
    command = (REPO_ROOT / "bin" / "studio.py").read_text(encoding="utf-8")
    wrapper = (REPO_ROOT / "bin" / "studio.sh").read_text(encoding="utf-8")

    for name in ("--bind", "--address", "--host", "--listen", "--interface", "--port"):
        assert name not in command, f"bin/studio.py declares {name}"
        assert f"{name}|" not in wrapper and f"{name})" not in wrapper, (
            f"bin/studio.sh accepts {name}"
        )

    tree = ast.parse(command)
    binds = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Server"
    ]
    assert len(binds) == 1, f"{len(binds)} sockets are bound in bin/studio.py"
    source = ast.unparse(binds[0])
    assert "studio.BIND_ADDRESS" in source, f"the socket is not bound to the constant: {source}"
    assert "0.0.0.0" not in command  # noqa: S104


def test_a_request_without_the_launch_cookie_is_refused(running: Any) -> None:
    started, _ = running
    status, _, _ = started.call("GET", "/", cookie=False)
    assert status == 401
    # The control: the same request with it.
    assert started.call("GET", "/")[0] == 200


def test_a_foreign_host_header_is_refused_as_misdirected(running: Any) -> None:
    """421, which is what a DNS-rebinding attempt looks like from in here."""
    started, _ = running
    status, _, _ = started.call("GET", "/", headers={"Host": f"evil.example:{started.port}"})
    assert status == 421
    assert started.call("GET", "/")[0] == 200


def test_a_foreign_origin_is_refused_and_the_own_origin_passes(running: Any) -> None:
    started, _ = running
    assert started.call("GET", "/", headers={"Origin": "http://attacker.example"})[0] == 403
    assert started.call("GET", "/", headers={"Origin": f"http://{started.bound}"})[0] == 200
    # An absent Origin is not a foreign one: a same-origin navigation sends none.
    assert started.call("GET", "/")[0] == 200


def test_options_is_refused_so_no_preflight_succeeds(running: Any) -> None:
    """405, and it is what makes the custom header worth requiring.

    A cross-origin page cannot set `X-Apg-Studio` without a preflight, and a
    preflight that is answered 405 is a request the browser never follows.
    """
    started, _ = running
    assert started.call("OPTIONS", "/__apg/state")[0] == 405
    assert started.call("OPTIONS", "/")[0] == 405
    assert started.call("GET", "/__apg/state")[0] == 200


def test_a_forwarded_call_needs_the_custom_header(running: Any) -> None:
    started, _ = running
    assert started.call("GET", "/__apg/state", custom=False)[0] == 403
    assert started.call("GET", "/__apg/state")[0] == 200
    # The assets are not forwarded calls and do not require it.
    assert started.call("GET", "/studio.css", custom=False)[0] == 200


def test_a_refused_post_does_not_read_its_body_and_does_not_hang(running: Any) -> None:
    """Rig 24a's measurement, against the product's own handler.

    A megabyte is announced and one byte is sent. The refusal has to be written
    without reading `self.rfile`, and the connection has to close rather than
    wait for the rest -- otherwise a page could hold a thread open by promising
    bytes it never sends.
    """
    started, _ = running
    connection = http.client.HTTPConnection("127.0.0.1", started.port, timeout=5)
    try:
        connection.putrequest("POST", "/__apg/query", skip_host=True, skip_accept_encoding=True)
        connection.putheader("Host", started.bound)
        connection.putheader("Cookie", f"{studio.LAUNCH_COOKIE}={started.key}")
        connection.putheader("Content-Length", "1000000")
        connection.endheaders()
        connection.send(b"x")
        response = connection.getresponse()
        assert response.status == 403
        assert response.getheader("Connection") == "close"
        response.read()
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# STU-SUPPLY-001 and STU-TOKEN-001, at the server
# ---------------------------------------------------------------------------


#: The headers every response must carry, written out HERE rather than read
#: from the product.
#:
#: **The first version of this proof iterated `studio.SECURITY_HEADERS`, and a
#: mutation that deleted a header from that dict passed it** (Run 3's battery,
#: M6): the expectation and the thing expected were one object, so removing a
#: header removed it from both sides at once. That is CLAUDE.md section 7's
#: sixth question -- does the fixture share the code's belief -- and this is the
#: answer to it. The values are ADR 0205's and the session plan's section 8;
#: changing them means editing this list, which is a decision somebody reviews.
EXPECTED_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}


def test_every_response_carries_the_csp_and_security_headers(running: Any) -> None:
    """Including refusals and the redirect: a response without them opted out.

    `services/docs/serve.py` wrote that sentence for its own 301 and it is the
    same argument here.

    Asserted against `EXPECTED_SECURITY_HEADERS` above, which is this module's
    own, and the product's dict is compared to it as an EQUALITY in the same
    test -- so a header added to the product without being reviewed here is as
    red as one removed.
    """
    started, _ = running
    assert studio.SECURITY_HEADERS == EXPECTED_SECURITY_HEADERS, (
        "the product's security headers are not the reviewed set: added "
        f"{sorted(set(studio.SECURITY_HEADERS) - set(EXPECTED_SECURITY_HEADERS))}, removed "
        f"{sorted(set(EXPECTED_SECURITY_HEADERS) - set(studio.SECURITY_HEADERS))}"
    )
    for method, path, kwargs in (
        ("GET", "/", {}),
        ("GET", "/studio.js", {}),
        ("GET", "/__apg/state", {}),
        ("GET", "/", {"cookie": False}),
        ("OPTIONS", "/", {}),
        ("GET", f"/open/{started.key}", {"cookie": False}),
    ):
        _, headers, _ = started.call(method, path, **kwargs)
        for name, value in EXPECTED_SECURITY_HEADERS.items():
            assert headers.get(name) == value, f"{method} {path} is missing {name}"
    assert "'unsafe-inline'" not in EXPECTED_SECURITY_HEADERS["Content-Security-Policy"]


def test_the_launch_path_sets_an_httponly_samesite_cookie(running: Any) -> None:
    """The cookie is the page's whole credential, and it is not a token.

    `HttpOnly` so no script can read it; `SameSite=Strict` so no other site can
    cause it to be sent; `Path=/` so the assets and the forwarder share it.
    """
    started, _ = running
    status, headers, _ = started.call("GET", f"/open/{started.key}", cookie=False)
    assert status == 303
    assert headers["Location"] == "/"
    cookie = headers["Set-Cookie"]
    assert cookie.startswith(f"{studio.LAUNCH_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie
    assert FAKE_TOKEN not in cookie


def test_no_page_response_header_or_asset_carries_the_token(running: Any) -> None:
    """The token is in one process's memory and reaches nothing the page sees."""
    started, stand_in = running
    del stand_in
    for method, path in (
        ("GET", "/"),
        ("GET", "/studio.js"),
        ("GET", "/studio.css"),
        ("GET", "/__apg/state"),
        ("GET", "/__apg/me"),
        ("GET", "/__apg/sessions"),
        ("GET", "/__apg/schema"),
    ):
        _, headers, body = started.call(method, path)
        rendered = json.dumps(headers) + body.decode("utf-8", "replace")
        assert FAKE_TOKEN not in rendered, f"{method} {path} carries the access token"
        assert FAKE_REFRESH not in rendered, f"{method} {path} carries the refresh token"


def test_nothing_studio_prints_is_a_token_a_key_or_a_value(running: Any) -> None:
    """D1256, over both of one run's streams, asking each what it can answer.

    `http.server`'s default logger writes the request line, which carries the
    query string -- so this drives a request with a distinctive value in one and
    then scans what the process wrote.

    **The two streams are not the same question.** Nothing a caller sent may
    reach the LOG, the launch key included, which is what `redact_for_log`
    exists for. The ANNOUNCED lines are a person's own terminal and carry the
    launch URL, which is the key by construction -- a per-launch key printed
    nowhere would be a capability nobody could use, and the residual (a hostile
    local process reading the scrollback) is named in the threat model rather
    than pretended away.
    """
    started, _ = running
    started.call("GET", "/__apg/audit?agent_id=a-distinctive-filter-value")
    started.call("GET", f"/open/{started.key}")

    started.process.terminate()
    started.process.wait(timeout=15)
    announced = "\n".join(started.lines)
    announced += started.process.stdout.read() if started.process.stdout else ""
    logged = started.process.stderr.read() if started.process.stderr else ""

    # **The LOG carries none of them, including the launch key.** That is what
    # `redact_for_log` is for: `http.server`'s default logger would have written
    # the request line, and the request line for the launch is the key.
    for secret in (FAKE_TOKEN, FAKE_REFRESH, started.key, "a-distinctive-filter-value"):
        assert secret not in logged, f"{secret[:16]}… reached the log"
    assert "apg-studio GET /__apg/audit" in logged, (
        "the request was not logged at all, so this test could not have seen the query "
        f"string even if it were there: {logged[-400:]}"
    )
    assert "apg-studio GET /open/<key>" in logged, "the launch path was not redacted in the log"

    # **The announced lines carry the key and nothing else**, because the URL a
    # human opens IS the key -- a per-launch key printed nowhere would be a
    # capability nobody could use. The token, the refresh token and a caller's
    # filter value are a different matter and appear in neither stream.
    assert started.key in announced, "the launch URL did not carry the key"
    for secret in (FAKE_TOKEN, FAKE_REFRESH, "a-distinctive-filter-value"):
        assert secret not in announced, f"{secret[:16]}… was printed"


def test_studio_holds_no_key_and_verifies_nothing(running: Any) -> None:
    """A HOLDER, not a verifier (D1246, ADR 0170).

    Two halves. The import list: neither file imports anything that can check a
    signature. And the behaviour: a token the deployment refuses comes back as a
    classification, so Studio plainly did not decide anything about it itself.
    """
    started, stand_in = running
    for source in ("bin/studio.py", "src/agentic_postgres/studio.py"):
        tree = ast.parse((REPO_ROOT / source).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not imported & {"jwt", "jwks", "jose", "cryptography", "hmac"}, (
            f"{source} imports something that can verify a signature: {sorted(imported)}"
        )

    stand_in.answers["/auth/me"] = (401, {"error": "authentication_failed"})
    _, _, body = started.call("GET", "/__apg/me")
    assert json.loads(body) == {"status": "refused"}


def test_an_upstream_refusal_is_classified_and_its_body_is_not_relayed(running: Any) -> None:
    """D433, ADR 0139: the kind of no, never the upstream's prose.

    A 403 from PostgREST can carry a column name, a constraint or a role. None
    of that is this tool's to publish, and a page that showed it would be
    relaying an upstream's answer as its own.
    """
    started, stand_in = running
    stand_in.answers["/admin/agents"] = (403, {"error": REFUSAL_BODY, "detail": REFUSAL_BODY})
    status, _, body = started.call("GET", "/__apg/agents")
    assert status == 200
    assert json.loads(body) == {"status": "refused"}
    assert REFUSAL_BODY not in body.decode()

    stand_in.answers["/admin/agents"] = (500, {"error": REFUSAL_BODY})
    assert json.loads(started.call("GET", "/__apg/agents")[2]) == {"status": "upstream_failed"}
    stand_in.answers.pop("/admin/agents")
    assert json.loads(started.call("GET", "/__apg/agents")[2])["status"] == "ok"


def test_the_audit_view_takes_the_endpoints_own_filters_and_no_others(running: Any) -> None:
    """D1248: a filter upstream of the page's count is the thing being refused.

    `agent_id` and `owner_id` are the endpoint's; an `outcome` or a `since` would
    narrow the page BEFORE it is counted, which is how a viewer comes to ask for
    `outcome=served` and never learn there were refusals.
    """
    started, _ = running
    assert started.call("GET", "/__apg/audit")[0] == 200
    assert started.call("GET", "/__apg/audit?agent_id=" + "0" * 8)[0] == 200
    status, _, body = started.call("GET", "/__apg/audit?outcome=refused")
    assert status == 400
    assert "outcome" in json.loads(body)["reason"]


def test_the_environment_is_not_read_for_a_credential() -> None:
    """No environment variable carries a password, and the source is the proof.

    `bin/dev-token.sh`'s rule allows a credential through an environment; Studio
    takes the narrower half because it has a TTY to ask at. A grep rather than a
    behaviour test, and named as one (D464): the assertion is that there is no
    read to behave with.
    """
    command = (REPO_ROOT / "bin" / "studio.py").read_text(encoding="utf-8")
    for reader in ("os.environ", "getenv", "environ["):
        assert reader not in command, f"bin/studio.py reads {reader}"
    assert "getpass" in command, "the prompt is the only other way in, and it is not there"


def test_studio_ignores_a_password_shaped_environment_variable(tmp_path: Path) -> None:
    """The behaviour half of the grep above, driven rather than read.

    A process that read `APG_STUDIO_PASSWORD` would launch; this one has no TTY
    and no `--password-file`, so it must refuse with exit 2 and say why.
    """
    stand_in = StandIn()
    stand_in.start()
    try:
        document = tmp_path / "outputs.json"
        document.write_text(json.dumps(stand_in.deployed()), encoding="utf-8")
        done = subprocess.run(
            [
                str(STUDIO), "--project", str(PROJECT), "--outputs", str(document),
                "--username", "ada",
            ],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
            stdin=subprocess.DEVNULL,
            env={**os.environ, **PASSWORD_SHAPED_VARIABLE},
        )  # fmt: skip
        assert done.returncode == 2, f"{done.returncode}: {done.stdout}{done.stderr}"
        assert "--password-file" in done.stderr
    finally:
        stand_in.stop()


def test_the_schema_view_is_refused_unless_the_surface_is_ok(tmp_path: Path) -> None:
    """`stale_contract` refuses the project views and keeps the release ones.

    The audit, agent and session views are operations of the APPLICATION -- they
    are the same on every deployment of this release -- so a contract
    disagreement about the project's REST surface says nothing about them. The
    schema and query views describe the project's own surface and are refused.
    """
    stand_in = StandIn()
    stand_in.start()
    started = None
    try:
        moved = stand_in.document()
        moved["info"]["title"] = moved["info"]["title"] + " (edited)"
        stand_in.answers[f"{REST_PATH}/"] = (200, moved)

        started = launch(tmp_path, stand_in)
        state = json.loads(started.call("GET", "/__apg/state")[2])
        assert state["surface"]["answer"] == "stale_contract"
        assert state["surface"]["served_sha256"] != state["surface"]["expected_sha256"]

        status, _, body = started.call("GET", "/__apg/schema")
        assert status == 409
        assert json.loads(body)["reason"] == "stale_contract"

        # The application views remain.
        assert started.call("GET", "/__apg/audit")[0] == 200
        assert started.call("GET", "/__apg/sessions")[0] == 200

        # And the launch line named both digests.
        printed = "\n".join(started.lines)
        assert "stale_contract" in printed
        assert "bin/apg.sh generate" in printed
    finally:
        if started is not None:
            started.process.terminate()
            started.process.wait(timeout=15)
        stand_in.stop()
