"""Session 39's public Postgres door, from off the host (ADR 0268).

The claim `public_port_scan` (EP-LIVE-002), and the module the customer proofs
of Run 7 extend (`public_endpoints_live`, EP-LIVE-001). Run from the
workstation, never the host, with no SSH: what is measured is what the internet
meets on the host's public address.

**The edge publishes 22's neighbours 80, 443 and 5432 and nothing else.** 5432
is the edge's `postgres` entrypoint: it answers only a TLS connection that names
a project's public host by SNI, and routes it to that project's customer
pooler. These proofs need no project with a door -- they are about what 5432
does for everybody else: a plaintext peer, a peer naming no project, a peer
naming a project that has no door. Each is refused, and none reaches a backend.

They replace `test_session4_public_transports.py`'s *"5432 is closed"* (D2338):
5432 is now open by design, so the stricter statement is what it answers.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import struct
import time
from pathlib import Path
from typing import Any

import pytest

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment("APG_PUBLIC_IPV4", "APG_PROJECT_A_OUTPUTS"),
]

#: What the public address answers on, and nothing else (ADR 0268, ADR 0246
#: item 2): SSH, the edge's HTTP and HTTPS, and the edge's Postgres door.
OPEN_PORTS = (22, 80, 443, 5432)

#: Ports that would mean the platform leaked: the platform pooler's and the
#: database's own ports, the edge's container ports, the socket proxy, a second
#: cluster. The project's allocated loopback ports are added from its document.
CLOSED_PORTS = (5433, 6432, 8080, 8082, 8089, 8432, 8443, 9000, 2375, 2376)

CONNECT_TIMEOUT = 5.0

#: The `postgres` entrypoint's read deadline is 10 s (rig 39a: plaintext refused
#: in 11.4 s). A peer is never held much past it.
DEADLINE_BOUND = 20.0

#: libpq's SSLRequest: length 8, code 1234.5679 (80877103).
SSL_REQUEST = struct.pack("!ii", 8, 80877103)


def port_is_open(host: str, port: int) -> bool:
    """Full TCP connect, not a SYN probe (`test_session2_public_edge`'s reason)."""
    try:
        with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT):
            return True
    except OSError:
        return False


def startup_message(user: str, database: str) -> bytes:
    """A protocol 3.0 StartupMessage, in plaintext -- what `sslmode=disable` sends."""
    body = struct.pack("!i", 196608)
    for key, value in (("user", user), ("database", database)):
        body += key.encode() + b"\0" + value.encode() + b"\0"
    body += b"\0"
    return struct.pack("!i", len(body) + 4) + body


@pytest.fixture(scope="module")
def public_ipv4() -> str:
    return os.environ["APG_PUBLIC_IPV4"]


@pytest.fixture(scope="module")
def project_a() -> dict[str, Any]:
    return json.loads(Path(os.environ["APG_PROJECT_A_OUTPUTS"]).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# EP-LIVE-002 -- the public address, scanned
# ---------------------------------------------------------------------------


def test_only_the_four_ports_answer(public_ipv4: str, project_a: dict[str, Any]) -> None:
    """22, 80, 443 and 5432 accept a connection; every port that would mean a
    platform leak does not -- including the project's own allocated loopback
    transports, read from its document. The open half is the control: a scanner
    that reports everything closed proves nothing (`test_session2_public_edge`).
    """
    shut = [port for port in OPEN_PORTS if not port_is_open(public_ipv4, port)]
    assert not shut, f"{public_ipv4}: expected open, found closed: {shut}"
    database = project_a["database"]
    allocated = [database[name]["port"] for name in ("pooled", "direct") if database[name]["port"]]
    leaked = [port for port in (*CLOSED_PORTS, *allocated) if port_is_open(public_ipv4, port)]
    assert not leaked, f"{public_ipv4} accepted a connection on {leaked}"


def test_plaintext_is_refused(public_ipv4: str, project_a: dict[str, Any]) -> None:
    """A StartupMessage with no TLS -- `sslmode=disable` -- never reaches an
    authentication exchange: the gateway routes nothing without a TLS name, and
    after its read deadline answers bytes that are not Postgres's `R` and
    closes. Bounded: a plaintext peer is not held past the deadline (D2326)."""
    started = time.monotonic()
    received = b""
    with socket.create_connection((public_ipv4, 5432), timeout=CONNECT_TIMEOUT) as peer:
        peer.settimeout(DEADLINE_BOUND)
        peer.sendall(startup_message(project_a["database"]["roles"]["app_runtime"], "postgres"))
        try:
            while chunk := peer.recv(4096):
                received += chunk
        except (TimeoutError, ConnectionResetError):
            pass
    elapsed = time.monotonic() - started
    assert not received.startswith(b"R"), (
        f"a plaintext peer reached authentication: {received[:40]!r}"
    )
    assert not received.startswith(b"E"), f"a plaintext peer reached a backend: {received[:80]!r}"
    assert elapsed < DEADLINE_BOUND, f"a plaintext peer was held {elapsed:.1f} s"


@pytest.mark.parametrize("server_name", ["absent", "nobody.invalid", "alpha-pool"])
def test_a_wrong_or_absent_sni_is_refused(
    public_ipv4: str, project_a: dict[str, Any], server_name: str
) -> None:
    """The gateway speaks Postgres's TLS -- it answers `SSLRequest` with `S`,
    which is the control that this port is the door and not a dead socket -- and
    then refuses the handshake of a peer that names no project (`sniStrict`), a
    name no project has, or the name a project WITHOUT endpoints would have
    (alpha's `pool.<domain>`: no router, so no certificate)."""
    names = {
        "absent": None,
        "nobody.invalid": "nobody.invalid",
        "alpha-pool": f"pool.{project_a['project']['domain']}",
    }
    with socket.create_connection((public_ipv4, 5432), timeout=CONNECT_TIMEOUT) as peer:
        peer.settimeout(DEADLINE_BOUND)
        peer.sendall(SSL_REQUEST)
        assert peer.recv(1) == b"S", "5432 did not answer SSLRequest: this is not the gateway"
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.set_alpn_protocols(["postgresql"])
        with pytest.raises((ssl.SSLError, ConnectionResetError, OSError)):
            with context.wrap_socket(peer, server_hostname=names[server_name]) as tls:
                tls.do_handshake()


def test_this_module_uses_no_ssh() -> None:
    """D2174's rule for a customer proof: nothing here reaches the host by any
    path but its public address. Read from this file's own text."""
    text = Path(__file__).read_text(encoding="utf-8")
    for needle in ("import " + "subprocess", "para" + "miko", '"s' + 'sh"', "ssh" + "_destination"):
        assert needle not in text, needle
