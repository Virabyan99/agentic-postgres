"""The SQL relay: admitted by `Origin` and a door name, bounded, verified, silent.

Session 44 (ADR 0286): `SQL-RELAY-001` (admission), `SQL-RELAY-002` (bounds),
`SQL-RELAY-003` (it holds and records nothing). `services/sql-relay/relay.py`
is imported and SERVED on a loopback port in this process, in front of a fake
door (an asyncio server that answers the SSLRequest and speaks TLS with a
certificate from a CA made in `tmp_path`) -- and, for the canary, run as its
own process exactly as the image runs it, in front of PostgreSQL from the
locked image with TLS on.

The test CA reaches the relay the way any trust store does: OpenSSL's
`SSL_CERT_FILE`, read by `ssl.create_default_context()`. The relay has no CA
parameter at all, and a guard below holds that (D2772).

The clients: a raw socket for every refusal before the upgrade (the status
line is the evidence), and `websockets`' synchronous client -- the dev lock's
17.1, the version the image pins (D2771) -- for sessions.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import contextlib
import datetime as dt
import hashlib
import hmac
import importlib.util
import os
import re
import secrets
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from tests.contract.test_image_contracts import LOCK, requires_docker
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from agentic_postgres import REPO_ROOT, naming

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

SERVICE = REPO_ROOT / "services" / "sql-relay"
RELAY_PY = SERVICE / "relay.py"
ZONE = "example.test"
ORIGIN = "https://control.example.test"
DOOR = "pool.slot3.example.test"
NAMES = (
    "pool.slot3.example.test",
    "direct.slot3.example.test",
    "dev.pool.slot3.example.test",
    "dev.direct.slot3.example.test",
    "pool.slot4.example.test",
    "direct.slot4.example.test",
    "pool.slot5.example.test",
    "direct.slot5.example.test",
    "pool.slot6.example.test",
)


def _load_relay() -> Any:
    specification = importlib.util.spec_from_file_location("apg_sql_relay", RELAY_PY)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules["apg_sql_relay"] = module
    specification.loader.exec_module(module)
    return module


relay_module = _load_relay()


# -- certificates ------------------------------------------------------------


class Authority:
    """A throwaway CA and the server certificates it signs."""

    def __init__(self, directory: Path, name: str) -> None:
        self.directory = directory
        self.key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        now = dt.datetime.now(dt.UTC)
        self.certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(self.key, hashes.SHA256())
        )
        self.pem = directory / f"{name}.pem"
        self.pem.write_bytes(self.certificate.public_bytes(serialization.Encoding.PEM))

    def issue(self, names: tuple[str, ...], stem: str) -> tuple[Path, Path]:
        key = ec.generate_private_key(ec.SECP256R1())
        now = dt.datetime.now(dt.UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
            .issuer_name(self.certificate.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), False)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), False)
            .sign(self.key, hashes.SHA256())
        )
        cert_path = self.directory / f"{stem}.crt"
        key_path = self.directory / f"{stem}.key"
        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        return cert_path, key_path


@pytest.fixture(scope="module")
def authorities(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    directory = tmp_path_factory.mktemp("sql-relay-ca")
    trusted = Authority(directory, "trusted-ca")
    stranger = Authority(directory, "stranger-ca")
    cert, key = trusted.issue(NAMES, "door")
    return {"trusted": trusted, "stranger": stranger, "cert": cert, "key": key}


# -- one event loop for the relay and the fake door --------------------------


class Loop:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    def run(self, coroutine: Any, timeout: float = 30) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout)

    def close(self) -> None:
        async def cancel_the_rest() -> None:
            rest = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in rest:
                task.cancel()
            await asyncio.gather(*rest, return_exceptions=True)

        with contextlib.suppress(Exception):
            self.run(cancel_the_rest(), timeout=10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)


class FakeDoor:
    """A door: SSLRequest answered `S`, then TLS, then `mode`.

    `echo` sends back what it reads; `stream:<n>` writes n bytes and waits;
    `silent` reads and says nothing; `plaintext` answers `N` and closes;
    `mute` never answers the SSLRequest; `slow:<s>` waits s seconds before `S`
    and then echoes."""

    def __init__(self, cert: Path, key: Path, mode: str = "echo") -> None:
        self.mode = mode
        self.connections = 0
        self.alpn: list[str | None] = []
        self.received = bytearray()
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(cert, key)
        self.context.set_alpn_protocols(["postgresql"])
        self.server: asyncio.Server | None = None

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server:
            self.server.close()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        try:
            request = await reader.readexactly(8)
            assert request == relay_module.SSL_REQUEST
            if self.mode == "mute":
                await asyncio.sleep(60)
                return
            if self.mode == "plaintext":
                writer.write(b"N")
                await writer.drain()
                return
            if self.mode.startswith("slow:"):
                await asyncio.sleep(float(self.mode.split(":")[1]))
            writer.write(b"S")
            await writer.drain()
            await writer.start_tls(self.context)
            self.alpn.append(writer.get_extra_info("ssl_object").selected_alpn_protocol())
            if self.mode.startswith("stream:"):
                writer.write(b"\0" * int(self.mode.split(":")[1]))
                await writer.drain()
                await asyncio.sleep(60)
            while data := await reader.read(65536):
                self.received.extend(data)
                if self.mode != "silent":
                    writer.write(data)
                    await writer.drain()
        except (OSError, ssl.SSLError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()


class Served:
    def __init__(self, loop: Loop, relay: Any, server: Any, door: FakeDoor, lines: list[str]):
        self.loop, self.relay, self.server, self.door, self.lines = loop, relay, server, door, lines
        self.port = server.sockets[0].getsockname()[1]

    def url(self, door: str = DOOR) -> str:
        return f"ws://127.0.0.1:{self.port}/v1/door/{door}"

    def session(self, door: str = DOOR, *, origin: str = ORIGIN, **headers: str) -> Any:
        return connect(
            self.url(door), origin=origin, additional_headers=headers or None,
            max_size=None, open_timeout=10, close_timeout=5,
        )  # fmt: skip

    def raw(self, path: str, *, origin: str | None = ORIGIN) -> str:
        """The status line the relay answers a handshake with."""
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as s:
            lines = [
                f"GET {path} HTTP/1.1", f"Host: sql.{ZONE}", "Upgrade: websocket",
                "Connection: Upgrade", "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
                "Sec-WebSocket-Version: 13",
            ]  # fmt: skip
            if origin is not None:
                lines.append(f"Origin: {origin}")
            s.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
            return s.recv(4096).decode(errors="replace").split("\r\n", 1)[0]


@pytest.fixture
def served(authorities: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """`served(mode, ca=...)` -> a relay in front of a fake door, torn down after."""
    loop = Loop()
    started: list[Served] = []

    def start(mode: str = "echo", ca: str = "trusted", door_port: int | None = None) -> Served:
        monkeypatch.setenv("SSL_CERT_FILE", str(authorities[ca].pem))
        monkeypatch.delenv("SSL_CERT_DIR", raising=False)
        door = FakeDoor(authorities["cert"], authorities["key"], mode)
        port = door_port if door_port is not None else loop.run(door.start())
        config = relay_module.Configuration(8080, ORIGIN, ZONE, "127.0.0.1", port)
        lines: list[str] = []
        relay = relay_module.Relay(config, log=lines.append)
        server = loop.run(relay.serve("127.0.0.1", 0))
        one = Served(loop, relay, server, door, lines)
        started.append(one)
        return one

    yield start

    async def stop(one: Served) -> None:
        one.server.close()
        await one.server.wait_closed()
        await one.door.stop()

    for one in started:
        with contextlib.suppress(Exception):
            loop.run(stop(one), timeout=10)
    loop.close()


def closed_with(session: Any, timeout: float = 10) -> int | None:
    """Read until the relay closes; the code it closed with."""
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            session.recv(timeout=max(0.1, deadline - time.monotonic()))
    except ConnectionClosed as closed:
        return closed.rcvd.code if closed.rcvd else None
    except TimeoutError:
        return None
    return None


# -- SQL-RELAY-001: admission ------------------------------------------------


def test_a_foreign_origin_is_refused_before_the_upgrade(served: Any) -> None:
    one = served()
    assert one.raw(f"/v1/door/{DOOR}", origin="https://evil.example") == "HTTP/1.1 403 Forbidden"
    assert one.raw(f"/v1/door/{DOOR}", origin=ORIGIN + ".evil.example").startswith("HTTP/1.1 403")
    assert one.raw(f"/v1/door/{DOOR}", origin="http://control.example.test").startswith(
        "HTTP/1.1 403"
    )
    assert one.door.connections == 0, "a refused handshake reached the door"
    assert one.lines == ["apg-sql-relay refused reason=origin"] * 3
    # The control: the console's own origin is upgraded.
    assert one.raw(f"/v1/door/{DOOR}") == "HTTP/1.1 101 Switching Protocols"


def test_no_origin_is_refused(served: Any) -> None:
    one = served()
    assert one.raw(f"/v1/door/{DOOR}", origin=None) == "HTTP/1.1 403 Forbidden"
    assert one.door.connections == 0


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/v1/door/",
        "/v2/door/pool.slot3.example.test",
        "/v1/door/pool.example.test",
        "/v1/door/control.example.test",
        "/v1/door/example.test",
        "/v1/door/api.slot3.example.test",
        "/v1/door/POOL.slot3.example.test",
        "/v1/door/pool.slot3.example.test.evil.test",
        "/v1/door/a.b.pool.slot3.example.test",
        "/v1/door/pool.slot3.example.testx",
        "/v1/door/pool.slot3.example.test/",
        "/v1/door/pool.slot3.example.test?x=1",
        "/v1/door/-x.pool.slot3.example.test",
    ],
)
def test_only_a_door_name_is_accepted(served: Any, path: str) -> None:
    one = served()
    assert one.raw(path) == "HTTP/1.1 400 Bad Request", path
    assert one.door.connections == 0
    assert one.lines == ["apg-sql-relay refused reason=path"]
    # The control: every door name the grammar admits is upgraded.
    for name in NAMES[:4]:
        assert one.raw(f"/v1/door/{name}") == "HTTP/1.1 101 Switching Protocols", name


@pytest.mark.parametrize(
    "door",
    [
        "127.0.0.1",
        "15.204.231.45",
        "pool.slot3.example.test:5432",
        "127.0.0.1:5432",
        "[::1]",
        "%5B::1%5D",
        "pool.slot3.example.test%2e",
        "localhost",
        "apg-edge-proxy",
    ],
)
def test_an_address_or_a_port_is_refused(served: Any, door: str) -> None:
    one = served()
    assert one.raw(f"/v1/door/{door}") == "HTTP/1.1 400 Bad Request", door
    assert one.door.connections == 0, "an address reached a socket"


def test_the_grammar_agrees_with_naming() -> None:
    """D2740: every name `naming` derives for a slot's doors, under the zone,
    matches; nothing else the zone holds does."""
    zone = "agenticpostgresql.com"
    grammar = relay_module.door_pattern(zone)
    derived = []
    for slot in ("slot1", "slot3", "slot8", "slot99"):
        domain = f"{slot}.{zone}"
        derived += naming.endpoint_hosts(domain)
        for branch in ("dev", "qa1", "feature12345"):
            derived += naming.branch_endpoint_hosts(domain, branch)
    assert all(grammar.fullmatch(name) for name in derived), [
        n for n in derived if not grammar.fullmatch(n)
    ]
    for other in (
        f"control.{zone}", zone, f"api.slot3.{zone}", f"pool.{zone}", f"slot3.{zone}",
        f"sql.{zone}", f"secrets.{zone}", f"www.{zone}", "pool.slot3.agenticpostgresql.co",
    ):  # fmt: skip
        assert not grammar.fullmatch(other), other


def test_health_answers_without_an_origin(served: Any) -> None:
    one = served()
    with socket.create_connection(("127.0.0.1", one.port), timeout=10) as s:
        s.sendall(b"GET /__apg/healthz HTTP/1.1\r\nHost: x\r\n\r\n")
        answer = s.recv(4096).decode()
    assert answer.startswith("HTTP/1.1 200 OK") and answer.endswith('{"status":"ok"}\n')
    assert one.door.connections == 0


def test_a_malformed_environment_refuses_to_start() -> None:
    good = {
        "APG_SQL_RELAY_PORT": "8080",
        "APG_SQL_RELAY_ALLOWED_ORIGIN": ORIGIN,
        "APG_SQL_RELAY_ZONE": ZONE,
        "APG_SQL_RELAY_UPSTREAM": "apg-edge-proxy:8432",
    }
    config = relay_module.configuration(good)
    assert config == relay_module.Configuration(8080, ORIGIN, ZONE, "apg-edge-proxy", 8432)
    bad = [
        ("APG_SQL_RELAY_PORT", ""), ("APG_SQL_RELAY_PORT", "0"), ("APG_SQL_RELAY_PORT", "http"),
        ("APG_SQL_RELAY_ALLOWED_ORIGIN", "https://control.example.test/"),
        ("APG_SQL_RELAY_ALLOWED_ORIGIN", "http://control.example.test"),
        ("APG_SQL_RELAY_ALLOWED_ORIGIN", "*"),
        ("APG_SQL_RELAY_ALLOWED_ORIGIN", "https://control.example.test:8443"),
        ("APG_SQL_RELAY_ZONE", "test"), ("APG_SQL_RELAY_ZONE", "Example.test"),
        ("APG_SQL_RELAY_UPSTREAM", "apg-edge-proxy"), ("APG_SQL_RELAY_UPSTREAM", "a:99999"),
        ("APG_SQL_RELAY_UPSTREAM", "http://apg-edge-proxy:8432"),
    ]  # fmt: skip
    for name, value in bad:
        with pytest.raises(relay_module.Refused):
            relay_module.configuration({**good, name: value})
    for name in good:
        with pytest.raises(relay_module.Refused):
            relay_module.configuration({k: v for k, v in good.items() if k != name})
    # As the image runs it: nothing set -> exit 2, one line, before any socket.
    environment = {k: v for k, v in os.environ.items() if not k.startswith("APG_SQL_RELAY_")}
    started = subprocess.run(
        [sys.executable, str(RELAY_PY)], env=environment, capture_output=True, text=True,
        timeout=60, check=False,
    )  # fmt: skip
    assert started.returncode == 2
    assert started.stdout == ""
    assert started.stderr == "apg-sql-relay refused to start: APG_SQL_RELAY_PORT is not set\n"


# -- SQL-RELAY-002: bounds ---------------------------------------------------


def _eventually(predicate: Any, timeout: float = 5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_the_ceilings_refuse_the_next_session(served: Any) -> None:
    one = served("silent")
    with contextlib.ExitStack() as stack:

        def hold(door: str, source: str) -> Any:
            return stack.enter_context(one.session(door, **{"X-Real-Ip": source}))

        # Four on one door, from four sources: the fifth on that door is refused.
        held = [hold(DOOR, f"198.51.100.{i}") for i in range(4)]
        assert closed_with(hold(DOOR, "198.51.100.9")) == relay_module.CLOSE_CEILING
        # Four from one source, on four doors: the fifth from that source is refused.
        held += [hold(name, "203.0.113.7") for name in NAMES[1:5]]
        assert closed_with(hold(NAMES[5], "203.0.113.7")) == relay_module.CLOSE_CEILING
        # Thirty-two in all: the thirty-third is refused, wherever it comes from.
        index = 0
        while len(held) < relay_module.MAX_SESSIONS:
            held.append(hold(NAMES[1 + index % 8], f"192.0.2.{index}"))
            index += 1
        assert _eventually(lambda: one.relay.total == relay_module.MAX_SESSIONS)
        assert closed_with(hold(NAMES[8], "192.0.2.250")) == relay_module.CLOSE_CEILING
        assert _eventually(
            lambda: sum("outcome=refused code=4429" in line for line in one.lines) == 3
        ), one.lines
        # The control: one session closed frees its place.
        held.pop().close()
        assert _eventually(lambda: one.relay.total == relay_module.MAX_SESSIONS - 1)
        assert closed_with(hold(NAMES[8], "192.0.2.251"), timeout=1) is None
        assert one.relay.total == relay_module.MAX_SESSIONS


def test_an_idle_session_is_closed(served: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relay_module, "IDLE_SECONDS", 0.6)  # patched small; the module says 300
    monkeypatch.setattr(relay_module, "TICK_SECONDS", 0.05)
    one = served("echo")
    started = time.monotonic()
    with one.session() as idle:
        assert closed_with(idle, timeout=5) == relay_module.CLOSE_TIME
    assert 0.5 < time.monotonic() - started < 3
    # The control: a session that keeps talking is not idle.
    with one.session() as talking:
        for _ in range(8):
            talking.send(b"x")
            assert talking.recv(timeout=5) == b"x"
            time.sleep(0.2)
    assert any("outcome=closed code=4408" in line for line in one.lines)
    assert relay_module.IDLE_SECONDS == 0.6 and relay_module.TOTAL_SECONDS == 1800.0


def test_a_session_is_closed_at_its_total(served: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relay_module, "TOTAL_SECONDS", 1.0)  # patched small; the module says 1800
    monkeypatch.setattr(relay_module, "TICK_SECONDS", 0.05)
    one = served("echo")
    started = time.monotonic()
    code = None
    with one.session() as busy:
        try:
            while time.monotonic() - started < 5:
                busy.send(b"x")
                busy.recv(timeout=5)
                time.sleep(0.1)
        except ConnectionClosed as closed:
            code = closed.rcvd.code if closed.rcvd else None
    assert code == relay_module.CLOSE_TIME
    assert 0.9 < time.monotonic() - started < 3


def test_a_large_message_is_refused(served: Any) -> None:
    one = served("echo")
    with one.session() as session:
        # The door first: before it is ready the relay holds at most 64 KiB
        # (`test_the_byte_caps_close_the_session`), and a megabyte sent then
        # meets that cap, not this one -- measured on CI's slower runner.
        session.send(b"ready?")
        assert session.recv(timeout=10) == b"ready?"
        session.send(b"\1" * relay_module.MAX_MESSAGE_BYTES)
        got = 0
        while got < relay_module.MAX_MESSAGE_BYTES:
            got += len(session.recv(timeout=10))
        assert got == relay_module.MAX_MESSAGE_BYTES  # the control: exactly the limit passes
        session.send(b"\1" * (relay_module.MAX_MESSAGE_BYTES + 1))
        assert closed_with(session) == 1009


def test_the_byte_caps_close_the_session(served: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # Towards the browser: patched to 256 KiB (the module says 64 MiB).
    monkeypatch.setattr(relay_module, "MAX_DOWN_BYTES", 256 << 10)
    streaming = served(f"stream:{1 << 20}")
    with streaming.session() as session:
        assert closed_with(session) == relay_module.CLOSE_TOO_MUCH
    with served(f"stream:{128 << 10}").session() as control:  # the control: under the cap
        got = 0
        while got < 128 << 10:
            got += len(control.recv(timeout=10))
    # Before the door is ready: 64 KiB held, one byte more closes the session.
    with served("slow:1.5").session() as early:
        early.send(b"\2" * (relay_module.MAX_PENDING_BYTES + 1))
        assert closed_with(early) == relay_module.CLOSE_TOO_MUCH
    slow = served("slow:0.5")
    with slow.session() as held:  # the control: under the cap, delivered once ready
        held.send(b"\3" * 1024)
        assert held.recv(timeout=10) == b"\3" * 1024


def test_a_text_frame_is_refused(served: Any) -> None:
    one = served("echo")
    with one.session() as session:
        session.send(b"bytes")
        assert session.recv(timeout=5) == b"bytes"  # the control
        session.send("text")
        assert closed_with(session) == relay_module.CLOSE_TEXT_FRAME


def test_the_relay_pings(served: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relay_module, "PING_SECONDS", 0.3)  # patched small; the module says 20
    one = served("silent")
    with socket.create_connection(("127.0.0.1", one.port), timeout=5) as s:
        s.sendall(
            (
                f"GET /v1/door/{DOOR} HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\n"
                "Connection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                f"Sec-WebSocket-Version: 13\r\nOrigin: {ORIGIN}\r\n\r\n"
            ).encode()
        )
        data = b""
        while b"\r\n\r\n" not in data:
            data += s.recv(4096)
        frames = data.split(b"\r\n\r\n", 1)[1]
        deadline = time.monotonic() + 3
        while len(frames) < 2 and time.monotonic() < deadline:
            frames += s.recv(4096)
    assert frames[0] & 0x0F == 0x9, f"the first frame is not a ping: {frames[:4]!r}"


# -- SQL-RELAY-003: it holds and records nothing -----------------------------


def test_the_relay_reads_no_secret_and_no_file() -> None:
    """The relay's source opens no file, reads only its four names from the
    environment, calls nothing over HTTP, and has no way to take a CA (D2772)."""
    source = RELAY_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert not calls & {
        "open",
        "read_text",
        "read_bytes",
        "load_verify_locations",
        "load_cert_chain",
        "urlopen",
    }
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (
            node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")]
        )
    }
    assert imported <= {
        "__future__", "asyncio", "logging", "os", "re", "secrets", "ssl", "struct", "sys",
        "time", "collections", "typing", "websockets",
    }, imported  # fmt: skip
    assert set(re.findall(r'"(APG_[A-Z_]+)"', source)) == {
        "APG_SQL_RELAY_PORT", "APG_SQL_RELAY_ALLOWED_ORIGIN", "APG_SQL_RELAY_ZONE",
        "APG_SQL_RELAY_UPSTREAM",
    }  # fmt: skip
    for word in ("cafile", "capath", "cadata", "/run/secrets", "SECRET", "TOKEN", "PASSWORD"):
        assert word not in source, word
    dockerfile = (SERVICE / "Dockerfile").read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["python", "-u", "/app/relay.py"]' in dockerfile.splitlines()
    assert '"websockets==${WEBSOCKETS_VERSION}"' in dockerfile
    assert "COPY relay.py /app/relay.py" in dockerfile and dockerfile.count("COPY") == 1


def test_the_door_is_verified(served: Any) -> None:
    trusted = served("echo")
    with trusted.session() as session:  # the control: the CA that signed the door
        session.send(b"hello")
        assert session.recv(timeout=10) == b"hello"
    assert trusted.door.alpn == ["postgresql"]
    stranger = served("echo", ca="stranger")
    with stranger.session() as session:
        assert closed_with(session) == relay_module.CLOSE_UNREACHABLE
    assert stranger.door.received == b"", "bytes crossed an unverified handshake"
    # A name the certificate does not carry: the hostname check refuses it.
    with trusted.session("pool.slot9.example.test") as session:
        assert closed_with(session) == relay_module.CLOSE_UNREACHABLE


def test_an_unreachable_door_is_reported_unreachable(
    served: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(relay_module, "CONNECT_SECONDS", 0.5)  # patched small; the module says 10
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    nobody = served(door_port=free)
    for one in (nobody, served("plaintext"), served("mute")):
        with one.session() as session:
            code = closed_with(session)
        assert code == relay_module.CLOSE_UNREACHABLE
        assert _eventually(lambda one=one: bool(one.lines)), "no line was written"
        line = one.lines[-1]
        assert " outcome=unreachable code=4502 " in line, line
        assert "asleep" not in line


# -- the canary: a real PostgreSQL, the relay as the image runs it ------------


def _message(kind: bytes, body: bytes) -> bytes:
    return kind + struct.pack("!i", len(body) + 4) + body


class Wire:
    """PostgreSQL's protocol over the WebSocket, the minimum the canary needs."""

    def __init__(self, session: Any) -> None:
        self.session = session
        self.buffer = b""

    def next(self) -> tuple[bytes, bytes]:
        while True:
            if len(self.buffer) >= 5:
                length = struct.unpack("!i", self.buffer[1:5])[0]
                if len(self.buffer) >= 1 + length:
                    kind, body = self.buffer[:1], self.buffer[5 : 1 + length]
                    self.buffer = self.buffer[1 + length :]
                    return kind, body
            self.buffer += self.session.recv(timeout=15)

    def login(self, user: str, password: str) -> dict[str, str]:
        params = f"user\0{user}\0database\0postgres\0\0".encode()
        self.session.send(struct.pack("!ii", len(params) + 8, 196608) + params)
        kind, body = self.next()
        assert kind == b"R" and struct.unpack("!i", body[:4])[0] == 10, (kind, body[:4])
        nonce = base64.b64encode(secrets.token_bytes(18)).decode()
        first_bare = f"n=,r={nonce}"
        first = f"n,,{first_bare}".encode()
        self.session.send(
            _message(b"p", b"SCRAM-SHA-256\0" + struct.pack("!i", len(first)) + first)
        )
        kind, body = self.next()
        server_first = body[4:].decode()
        attrs = dict(part.split("=", 1) for part in server_first.split(","))
        salted = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.b64decode(attrs["s"]), int(attrs["i"])
        )
        client_key = hmac.new(salted, b"Client Key", "sha256").digest()
        final_bare = f"c=biws,r={attrs['r']}"
        auth = f"{first_bare},{server_first},{final_bare}".encode()
        signature = hmac.new(hashlib.sha256(client_key).digest(), auth, "sha256").digest()
        proof = base64.b64encode(
            bytes(a ^ b for a, b in zip(client_key, signature, strict=True))
        ).decode()
        self.session.send(_message(b"p", f"{final_bare},p={proof}".encode()))
        kind, body = self.next()
        assert kind == b"R" and struct.unpack("!i", body[:4])[0] == 12, body
        while self.next()[0] != b"Z":
            pass
        return {"nonce": nonce, "server_first": server_first, "proof": proof}

    def query(self, sql: str) -> tuple[list[str], str | None]:
        self.session.send(_message(b"Q", sql.encode() + b"\0"))
        rows: list[str] = []
        error = None
        while True:
            kind, body = self.next()
            if kind == b"D":
                length = struct.unpack("!i", body[2:6])[0]
                rows.append(body[6 : 6 + length].decode())
            elif kind == b"E":
                fields = dict((part[:1], part[1:].decode()) for part in body.split(b"\0") if part)
                error = fields.get(b"C")
            elif kind == b"Z":
                return rows, error


@pytest.fixture(scope="module")
def tls_postgres(
    authorities: dict[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Any]:
    """PostgreSQL from the locked image, TLS on with a certificate for the door's
    name, a SCRAM password for `postgres`; removed with its volume (D2098)."""
    if subprocess.run(["docker", "info"], capture_output=True, check=False).returncode:
        pytest.skip("the Docker daemon is unreachable")
    directory = tmp_path_factory.mktemp("sql-relay-pg")
    for name in ("door.crt", "door.key"):
        (directory / name).write_bytes((authorities["cert"].parent / name).read_bytes())
    os.chmod(directory, 0o755)  # noqa: S103 -- the container's postgres user copies them
    for path in directory.iterdir():
        os.chmod(path, 0o644)
    password = secrets.token_urlsafe(24)
    name = f"apg-sql-relay-test-{secrets.token_hex(4)}"
    script = (
        "set -e; cp /certs/door.crt /certs/door.key /tmp/; chown postgres /tmp/door.key; "
        "chmod 600 /tmp/door.key; exec docker-entrypoint.sh postgres -c ssl=on "
        "-c ssl_cert_file=/tmp/door.crt -c ssl_key_file=/tmp/door.key"
    )
    started = subprocess.run(
        ["docker", "run", "-d", "--name", name, "-e", f"POSTGRES_PASSWORD={password}",
         "-p", "127.0.0.1::5432", "-v", f"{directory}:/certs:ro", "--entrypoint", "sh",
         LOCK["POSTGRES_IMAGE"], "-c", script],
        capture_output=True, text=True, check=False, timeout=600,
    )  # fmt: skip
    assert started.returncode == 0, started.stderr
    try:
        port = int(
            subprocess.run(
                ["docker", "port", name, "5432/tcp"], capture_output=True, text=True, check=True
            )
            .stdout.strip()
            .rsplit(":", 1)[1]
        )
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            ready = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                capture_output=True, text=True, check=False,
            )  # fmt: skip
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            pytest.fail("PostgreSQL did not become ready")
        yield {"port": port, "password": password}
    finally:
        subprocess.run(["docker", "rm", "-fv", name], capture_output=True, check=False)


@requires_docker
def test_no_line_holds_the_payload(
    authorities: dict[str, Any], tls_postgres: dict[str, Any], tmp_path: Path
) -> None:
    """D2743's canary. The relay runs as its own process exactly as the image
    runs it (no argument, the four values in its environment), in front of
    PostgreSQL with TLS. A session logs in with SCRAM and a known password and
    runs a statement carrying a marker; every byte the process wrote to stdout
    and stderr is read. The control: the marker came back to the client, so it
    crossed the relay."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    environment = {
        **{k: v for k, v in os.environ.items() if not k.startswith(("APG_", "SSL_CERT"))},
        "APG_SQL_RELAY_PORT": str(port),
        "APG_SQL_RELAY_ALLOWED_ORIGIN": ORIGIN,
        "APG_SQL_RELAY_ZONE": ZONE,
        "APG_SQL_RELAY_UPSTREAM": f"127.0.0.1:{tls_postgres['port']}",
        "SSL_CERT_FILE": str(authorities["trusted"].pem),
    }
    out, err = tmp_path / "stdout", tmp_path / "stderr"
    with out.open("wb") as stdout, err.open("wb") as stderr:
        process = subprocess.Popen(
            [sys.executable, str(RELAY_PY)], env=environment, stdout=stdout, stderr=stderr
        )
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), 1):
                break
            time.sleep(0.1)
        marker = f"apg-s44-canary-{secrets.token_hex(6)}"
        url = f"ws://127.0.0.1:{port}/v1/door/{DOOR}"
        with connect(url, origin=ORIGIN, max_size=None) as session:
            wire = Wire(session)
            exchange = wire.login("postgres", tls_postgres["password"])
            rows, error = wire.query(f"SELECT '{marker}' /* {marker} */")
            assert (rows, error) == ([marker], None)  # the control
            # Refused, marker and all: a quoted identifier is an undefined
            # column whatever its hex digits are (unquoted, they parse either
            # as arithmetic or not at all).
            assert wire.query(f'SELECT "{marker}"')[1] == "42703"
        with connect(url, origin=ORIGIN, max_size=None) as session:
            session.send(b"\0\0\0\x08garbage-" + marker.encode())  # a malformed startup
            with contextlib.suppress(ConnectionClosed, TimeoutError):
                while True:
                    session.recv(timeout=5)
        time.sleep(0.5)
    finally:
        process.terminate()
        process.wait(10)
    written = out.read_bytes() + err.read_bytes()
    text = written.decode(errors="replace")
    for value in (
        tls_postgres["password"], marker, exchange["nonce"], exchange["proof"],
        exchange["server_first"], "SCRAM", "SELECT", "postgres\0", "garbage",
    ):  # fmt: skip
        assert value.encode() not in written, f"the relay wrote {value[:12]!r}..."
    lines = text.splitlines()
    assert err.read_bytes() == b"", text
    pattern = re.compile(
        rf"apg-sql-relay session=[0-9a-f]{{16}} door={re.escape(DOOR)} outcome=closed "
        r"code=\d+ seconds=\d+\.\d up=\d+ down=\d+"
    )
    assert len(lines) == 2 and all(pattern.fullmatch(line) for line in lines), lines
