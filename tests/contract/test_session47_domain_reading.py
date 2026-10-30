"""The domain proof's readings, held offline (Session 47 Run 12; ADR 0299, D2985).

`tests/external/test_session47_domain.py` (`domain_live`) runs only after the
cutover, against the public names. Two of its readings decide every verdict
it gives, and both are exercised here on a local stand-in (D1114: the proof's
own functions):

* `ask` READS a redirect and never follows it -- a 301 or 308 comes back as
  itself with its `Location`, and a POST stays the request it was;
* `certificate_names` speaks PostgreSQL's own `SSLRequest` before TLS on a
  door, and gives up when the server does not answer `S`.

The zone it reads is the build's (`site_build`), never a typed domain.
"""

from __future__ import annotations

import http.server
import socket
import struct
import threading
from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
from tests.external import test_session47_domain as domain_proof

from agentic_postgres import naming, site_build

pytestmark = [pytest.mark.contract, pytest.mark.p0]


class _Redirects(http.server.BaseHTTPRequestHandler):
    seen: ClassVar[list[tuple[str, str, str]]] = []

    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        _Redirects.seen.append((self.command, self.path, self.headers.get("User-Agent", "")))
        code = 308 if self.path.startswith("/api/") else 301
        self.send_response(code)
        self.send_header("Location", "https://new.example.test" + self.path)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = _answer
    do_POST = _answer

    def log_message(self, *args: Any) -> None:
        return None


@pytest.fixture
def redirects() -> Iterator[str]:
    _Redirects.seen = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Redirects)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_a_redirect_is_read_never_followed(redirects: str) -> None:
    status, headers, _ = domain_proof.ask("GET", redirects + domain_proof.PROBE_PATH)
    assert status == 301
    assert headers["Location"] == "https://new.example.test" + domain_proof.PROBE_PATH
    status, headers, _ = domain_proof.ask("POST", redirects + "/api/v1/sessions")
    assert (status, headers["Location"]) == (308, "https://new.example.test/api/v1/sessions")
    # Asked once each, as the proof's own agent (D2728); nothing followed the Location.
    assert _Redirects.seen == [
        ("GET", domain_proof.PROBE_PATH, domain_proof.USER_AGENT),
        ("POST", "/api/v1/sessions", domain_proof.USER_AGENT),
    ]


def test_a_door_is_asked_with_postgres_own_ssl_request() -> None:
    """The bytes are PostgreSQL's `SSLRequest` (length 8, code 80877103), and a
    server that answers `N` -- no TLS -- is a failed reading, not a pass."""
    assert domain_proof.SSL_REQUEST == struct.pack("!ii", 8, (1234 << 16) | 5679)
    listener = socket.create_server(("127.0.0.1", 0))
    received: list[bytes] = []

    def serve() -> None:
        connection, _ = listener.accept()
        with connection:
            received.append(connection.recv(8))
            connection.sendall(b"N")

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    port = listener.getsockname()[1]
    with pytest.raises(AssertionError, match="answered b'N' to SSLRequest"):
        domain_proof.certificate_names("127.0.0.1", port, postgres=True)
    thread.join(5)
    listener.close()
    assert received == [domain_proof.SSL_REQUEST]


def test_the_proof_reads_the_builds_zone() -> None:
    """The new zone is the control domain's (the site's apex), and the former
    one is not it -- so the redirect proof cannot ask a name of itself."""
    zone = naming.sql_relay_zone(site_build.CONTROL_DOMAIN)
    assert site_build.SITE_URL == f"https://{zone}"
    assert domain_proof.FORMER_ZONE != zone
    assert naming.sql_relay_host(site_build.CONTROL_DOMAIN) == f"sql.{zone}"
