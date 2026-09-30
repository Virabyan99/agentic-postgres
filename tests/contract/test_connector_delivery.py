"""The delivery pass: one signed POST, a fixed token, never a redirect (CONN-OUT-001).

ADR 0238, D1790, D1791, D1800, D1813. Each proof runs a REAL `http.server` on
127.0.0.1 answering programmed statuses, and `connector_delivery` sends to it
over its real opener -- so what is proved is the bytes that left, the status
that came back and the token that was recorded, not a fake transport's idea of
them. The signature is verified with this module's OWN `hmac` over the bytes
the server received, with a key this module derives itself; a signer and a
verifier written by one author out of one belief would agree about anything.

The repository is a fake that records `finish_delivery` and answers what the
substrate would; the substrate's retry arithmetic (`max + 1` attempts, then
`dead`) is `test_connectivity_substrate.py`'s, under a real cluster. What is
proved here is the loop's half: one attempt per claim, the token it records,
and that nothing it records or logs carries the URL, the payload or the key.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import socket
import ssl
import threading
import urllib.error
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import UUID, uuid4

import pytest

from agentic_postgres import service_source

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

delivery_module = service_source.load("connector_delivery")
worker = service_source.load("workflow_worker")

MASTER = "0f" * 32
LABEL = b"apg-connector-key-v1\x00"
PAYLOAD_MARKER = "payload-marker-7d1c"


@dataclass(frozen=True)
class Delivery:
    """`ClaimedDelivery`'s shape."""

    endpoint: str | None
    delivery_id: UUID = field(default_factory=uuid4)
    connector_name: str = "note-embedded"
    rehearsal: bool = False
    event_id: UUID = field(default_factory=uuid4)
    event_name: str = "note_embedding.set"
    event_version: int = 1
    emitted_at: datetime = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)
    payload: dict[str, Any] = field(default_factory=lambda: {"note_id": PAYLOAD_MARKER})
    attempt: int = 1
    max_attempts: int = 3


class Recorder:
    """The fake repository: records every call, answers a programmed status."""

    def __init__(self, deliveries: list[Any] | None = None, answers: list[str] | None = None):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._deliveries = list(deliveries or [])
        self._answers = list(answers or [])

    async def claim_delivery(self, **kwargs: Any) -> Any:
        self.calls.append(("claim_delivery", kwargs))
        return self._deliveries.pop(0) if self._deliveries else None

    async def finish_delivery(self, **kwargs: Any) -> str:
        self.calls.append(("finish_delivery", kwargs))
        return self._answers.pop(0) if self._answers else "delivered"

    async def fire_due(self) -> int:
        self.calls.append(("fire_due", {}))
        return 0

    def finished(self) -> list[dict[str, Any]]:
        return [kwargs for name, kwargs in self.calls if name == "finish_delivery"]


class Server:
    """A real HTTP server on 127.0.0.1 answering `statuses` in turn (then the last)."""

    def __init__(self, statuses: list[int], location: str | None = None) -> None:
        self.received: list[dict[str, Any]] = []
        received, programmed = self.received, list(statuses)

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                received.append(
                    {
                        "method": "POST",
                        "path": self.path,
                        "headers": dict(self.headers),
                        "body": body,
                    }
                )
                status = programmed.pop(0) if len(programmed) > 1 else programmed[0]
                self.send_response(status)
                if location is not None:
                    self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self) -> None:
                received.append({"method": "GET", "path": self.path, "headers": dict(self.headers)})
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *arguments: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def serve() -> Any:
    servers: list[Server] = []

    def make(statuses: list[int], location: str | None = None) -> Server:
        server = Server(statuses, location)
        servers.append(server)
        return server

    yield make
    for server in servers:
        server.close()


def deliver(delivery: Delivery, repository: Recorder, *, clock: Any = None) -> str:
    options = {} if clock is None else {"clock": clock}
    return asyncio.run(
        delivery_module.deliver(
            delivery, repository=repository, key_master_hex=MASTER, holder="h", **options
        )
    )


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


# ---------------------------------------------------------------------------
# The loop's share: one delivery per iteration, steps never starved
# ---------------------------------------------------------------------------


class Steps:
    """A step repository with one step always ready, and a counter."""

    def __init__(self) -> None:
        self.processed = 0
        self.names: list[str] = []

    async def heartbeat(self, **kwargs: Any) -> None:
        self.names.append("heartbeat")

    async def claim(self, **kwargs: Any) -> Any:
        self.names.append("claim")
        return object()


def test_one_delivery_per_iteration_and_a_step_is_not_starved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**D1790.** Five deliveries are due and a step is ready: one iteration
    processes the step AND claims exactly one delivery, then fires the
    schedule once. A retry storm cannot starve a step, and without the key the
    connector passes do not run at all (the control)."""
    steps = Steps()
    sent: list[Any] = []

    async def process(step: Any, **kwargs: Any) -> None:
        steps.processed += 1

    async def fake_deliver(delivery: Any, **kwargs: Any) -> str:
        sent.append(delivery)
        return "pending"

    monkeypatch.setattr(worker, "process", process)
    monkeypatch.setattr(worker.connector_delivery, "deliver", fake_deliver)
    connectors = Recorder([Delivery(endpoint="http://x") for _ in range(5)])

    asyncio.run(
        worker.run_forever(
            repository=steps,
            service=None,
            holder="h",
            once=True,
            connectors=connectors,
            connector_key=MASTER,
        )
    )
    assert steps.processed == 1
    assert len(sent) == 1
    assert [name for name, _ in connectors.calls] == ["claim_delivery", "fire_due"]
    (claim,) = [kwargs for name, kwargs in connectors.calls if name == "claim_delivery"]
    assert claim["lease_seconds"] == (
        delivery_module.DELIVERY_TIMEOUT_SECONDS + worker.lease_margin_seconds()
    )

    # The control: no key, no connector pass -- and the step still runs.
    control = Recorder([Delivery(endpoint="http://x")])
    asyncio.run(
        worker.run_forever(
            repository=steps,
            service=None,
            holder="h",
            once=True,
            connectors=control,
            connector_key=None,
        )
    )
    assert steps.processed == 2
    assert control.calls == []


def test_the_body_and_headers_are_canonical() -> None:
    """Sorted keys, no whitespace, UTF-8; the three `X-Apg-*` headers and
    nothing the receiver could mistake for a credential."""
    delivery = Delivery(endpoint="http://x")
    body = delivery_module.body(delivery)
    assert body == json.dumps(
        {
            "delivery_id": str(delivery.delivery_id),
            "event": "note_embedding.set",
            "version": 1,
            "event_id": str(delivery.event_id),
            "emitted_at": "2026-09-30T12:00:00+00:00",
            "payload": {"note_id": PAYLOAD_MARKER},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert b" " not in body

    headers = delivery_module.headers(delivery, "ab" * 32, body, now=1_790_000_000)
    assert set(headers) == {
        "Content-Type",
        "User-Agent",
        "X-Apg-Delivery",
        "X-Apg-Event",
        "X-Apg-Signature",
    }
    assert headers["Content-Type"] == "application/json"
    assert headers["User-Agent"] == delivery_module.USER_AGENT
    assert headers["X-Apg-Delivery"] == str(delivery.delivery_id)
    assert headers["X-Apg-Event"] == "note_embedding.set@1"
    assert headers["X-Apg-Signature"].startswith("t=1790000000,v1=")


def test_the_signature_verifies_independently(serve: Any) -> None:
    """The bytes the SERVER received, verified with this module's own HMAC
    under a key this module derived -- and a one-byte change fails."""
    server = serve([200])
    delivery = Delivery(endpoint=f"{server.url}/ok")
    deliver(delivery, Recorder(), clock=lambda: 1_790_000_123)

    (request,) = server.received
    headers = {name.lower(): value for name, value in request["headers"].items()}
    t, v1 = headers["x-apg-signature"].removeprefix("t=").split(",v1=")
    assert t == "1790000123"
    key = hmac.new(bytes.fromhex(MASTER), LABEL + b"note-embedded", hashlib.sha256).digest()
    signed = f"{t}.{headers['x-apg-delivery']}.".encode() + request["body"]
    assert hmac.compare_digest(hmac.new(key, signed, hashlib.sha256).hexdigest(), v1)
    tampered = signed[:-1] + bytes([signed[-1] ^ 1])
    assert not hmac.compare_digest(hmac.new(key, tampered, hashlib.sha256).hexdigest(), v1)
    assert json.loads(request["body"])["payload"] == {"note_id": PAYLOAD_MARKER}


def test_a_two_hundred_is_delivered_once(serve: Any) -> None:
    for status in (200, 201, 204):
        server = serve([status])
        repository = Recorder(answers=["delivered"])
        assert deliver(Delivery(endpoint=f"{server.url}/ok"), repository) == "delivered"
        assert len(server.received) == 1
        (finished,) = repository.finished()
        assert (finished["delivered"], finished["status"], finished["error"]) == (
            True,
            status,
            None,
        )


def test_a_five_hundred_is_retried_to_max_then_dead(serve: Any) -> None:
    """Three claims of one delivery with `max_attempts` 3: each is ONE POST
    recorded `http_500`, and the substrate's third answer is `dead`. The loop
    never retries inside an attempt -- the park is the backoff. The control: a
    receiver that recovers on the third attempt is delivered then."""
    server = serve([500])
    delivery = Delivery(endpoint=f"{server.url}/fail")
    repository = Recorder(answers=["pending", "pending", "dead"])
    verdicts = [deliver(delivery, repository) for _ in range(3)]
    assert verdicts == ["pending", "pending", "dead"]
    assert len(server.received) == 3
    assert {request["headers"]["X-Apg-Delivery"] for request in server.received} == {
        str(delivery.delivery_id)
    }
    assert [(f["delivered"], f["status"], f["error"]) for f in repository.finished()] == [
        (False, 500, "http_500")
    ] * 3

    recovering = serve([503, 503, 200])
    repository = Recorder(answers=["pending", "pending", "delivered"])
    for _ in range(3):
        deliver(Delivery(endpoint=f"{recovering.url}/ok"), repository)
    assert [f["error"] for f in repository.finished()] == ["http_503", "http_503", None]


def test_every_failure_is_a_fixed_token(serve: Any) -> None:
    """**D1813's table, each case driven.** A refused port and a READ timeout
    for real; the rest as the exceptions rig 34b measured. Every token is one
    of the fixed words, and none carries the host it failed to reach."""
    host = "apg-unreachable-host-4c1e.invalid"

    # Real: a port nothing listens on.
    port = closed_port()
    status, token = delivery_module._post(f"http://127.0.0.1:{port}/x", {}, b"{}", timeout=2)
    assert (status, token) == (None, "connect_failed")

    # Real: a server that accepts and never answers -> a BARE TimeoutError.
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        silent = listener.getsockname()[1]
        status, token = delivery_module._post(
            f"http://127.0.0.1:{silent}/x", {}, b"{}", timeout=0.5
        )
        assert (status, token) == (None, "timeout")
    finally:
        listener.close()

    cases = {
        "connect_failed": urllib.error.URLError(ConnectionRefusedError(111, "refused")),
        "timeout": urllib.error.URLError(TimeoutError(f"timed out reaching {host}")),
        "dns_failed": urllib.error.URLError(
            socket.gaierror(-2, f"Name or service not known {host}")
        ),
        "tls_failed": urllib.error.URLError(ssl.SSLCertVerificationError(f"self-signed {host}")),
        "unknown": ValueError(f"unknown url type: {host}"),
    }
    for expected, exc in cases.items():
        assert delivery_module.error_token(exc) == expected, expected
    assert delivery_module.error_token(TimeoutError("read")) == "timeout"
    assert set(cases) == set(delivery_module.ERROR_TOKENS)

    # A scheme other than http(s) is never opened.
    assert delivery_module._post("file:///etc/passwd", {}, b"{}", timeout=1) == (None, "unknown")

    # And what reaches the record is the token, never the text.
    repository = Recorder(answers=["pending"])
    deliver(Delivery(endpoint=f"http://127.0.0.1:{closed_port()}/x"), repository)
    (finished,) = repository.finished()
    assert finished["error"] == "connect_failed" and finished["status"] is None


def test_a_redirect_is_not_followed(serve: Any) -> None:
    """**D1812.** A 301/302/303/307/308 is the attempt's own result: the
    signed body is not re-sent anywhere and the redirect's target receives
    nothing -- neither a POST nor the bodiless GET the default opener sends."""
    target = serve([200])
    for code in (301, 302, 303, 307, 308):
        redirector = serve([code], location=f"{target.url}/elsewhere")
        repository = Recorder(answers=["pending"])
        deliver(Delivery(endpoint=f"{redirector.url}/ok"), repository)
        (finished,) = repository.finished()
        assert (finished["delivered"], finished["status"], finished["error"]) == (
            False,
            code,
            f"http_{code}",
        )
        assert len(redirector.received) == 1
    assert target.received == [], "a redirect was followed"


def test_a_lost_lease_redelivers(serve: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """At-least-once: a lease lost mid-send (`lease_lost`) means the same
    delivery is claimed again and POSTed again under the SAME delivery id --
    which is what the receiver deduplicates on."""
    server = serve([200])
    delivery = Delivery(endpoint=f"{server.url}/ok")
    connectors = Recorder([delivery, delivery], answers=["lease_lost", "delivered"])

    class NoSteps:
        async def heartbeat(self, **kwargs: Any) -> None:
            pass

        async def claim(self, **kwargs: Any) -> Any:
            return None

    for _ in range(2):
        asyncio.run(
            worker.run_forever(
                repository=NoSteps(),
                service=None,
                holder="h",
                once=True,
                connectors=connectors,
                connector_key=MASTER,
            )
        )
    assert len(server.received) == 2
    assert {r["headers"]["X-Apg-Delivery"] for r in server.received} == {str(delivery.delivery_id)}
    assert [f["delivered"] for f in connectors.finished()] == [True, True]


def test_no_record_carries_the_url_the_payload_or_the_key(
    serve: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """What is RECORDED -- every `finish_delivery` argument -- and what is
    LOGGED, over a success, a 500, a refused port and a pass that raises with
    the URL in its message, carries no URL, no payload value, no master and
    no derived key."""
    caplog.set_level(logging.DEBUG)
    derived = hmac.new(bytes.fromhex(MASTER), LABEL + b"note-embedded", hashlib.sha256).hexdigest()
    ok, failing = serve([200]), serve([500])
    refused = f"http://127.0.0.1:{closed_port()}/secret-path"
    repository = Recorder(answers=["delivered", "pending", "pending"])
    for endpoint in (f"{ok.url}/ok", f"{failing.url}/fail", refused):
        deliver(Delivery(endpoint=endpoint), repository)

    class Raising(Recorder):
        async def claim_delivery(self, **kwargs: Any) -> Any:
            raise RuntimeError(f"could not reach {refused} with {PAYLOAD_MARKER} {MASTER}")

    class NoSteps:
        async def heartbeat(self, **kwargs: Any) -> None:
            pass

        async def claim(self, **kwargs: Any) -> Any:
            return None

    asyncio.run(
        worker.run_forever(
            repository=NoSteps(),
            service=None,
            holder="h",
            once=True,
            connectors=Raising(),
            connector_key=MASTER,
        )
    )
    assert any("the delivery pass raised RuntimeError" in r.getMessage() for r in caplog.records)

    recorded = json.dumps(repository.finished(), default=str)
    logged = "\n".join(record.getMessage() for record in caplog.records)
    for secret in (ok.url, failing.url, refused, "127.0.0.1", PAYLOAD_MARKER, MASTER, derived):
        assert secret not in recorded, secret
        assert secret not in logged, secret


def test_a_rehearsal_is_sent_to_the_discard_port_and_never_the_endpoint(serve: Any) -> None:
    """D1801: a rehearsal's delivery goes to 127.0.0.1:9 whatever the row
    says -- here an endpoint that WOULD answer, which receives nothing."""
    server = serve([200])
    repository = Recorder(answers=["pending"])
    deliver(Delivery(endpoint=f"{server.url}/ok", rehearsal=True), repository)
    assert server.received == []
    (finished,) = repository.finished()
    assert finished["error"] == "connect_failed"
    assert delivery_module.REHEARSAL_ENDPOINT == "http://127.0.0.1:9/"
