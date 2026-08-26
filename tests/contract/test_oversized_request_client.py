"""D511: the client must not lose a refusal that arrived while it was writing.

The proof this supports (`API-AUTH-002`'s live half) sends 64 KiB and asserts the
edge answers **413**. Traefik refuses on `Content-Length` and closes while the
client is still writing, and `urllib` then discards the response it had already
received. Measured across one host trip at a single release: `ECONNRESET`, then
`EPIPE`, then a pass — three runs, three outcomes, nothing changed between them.

**The condition is constructed, not waited for**, and constructing it correctly
took two attempts. The first version of this module ran a server that answered
immediately and closed; every arm passed, **and every arm passed with the OLD
client too**. 64 KiB fits entirely in loopback socket buffers, so `sendall`
returned before the server had said anything and there was no race to lose. Six
green tests measuring nothing — D374's shape.

What the defect actually needs is a client still *blocked* in `sendall` when the
server gives up. That needs two things the first version had neither of: a tiny
``SO_RCVBUF`` on the listener, set before ``listen`` so the accepted socket
inherits it, and a server that **never drains the body**. The client's window
then closes and its write blocks, which is what happens over a real network
against Traefik. With that, `urllib` loses the response in both arms and the
repaired client recovers it — which is the measurement that makes the repair
worth having.

**The silent arm is what keeps the repair honest.** A server that closes
*without* answering must NOT yield 413. Without it, "tolerate a broken pipe" and
"recover the response" are indistinguishable, and the repair would be D509's
shape: a proof that goes green for exactly the defect it exists to detect — a
buffering middleware that is not attached, so the service reads the whole body
and the edge never refuses at all.
"""

from __future__ import annotations

import socket
import struct
import threading
import urllib.error
import urllib.request

import pytest
from tests.deployment.oversized_request import post_and_read_refusal

pytestmark = [pytest.mark.contract, pytest.mark.p0]

REFUSAL = b"HTTP/1.1 413 Request Entity Too Large\r\nContent-Length: 0\r\n\r\n"

#: Far larger than any socket buffer, so the write is still in progress when the
#: server answers. 64 KiB -- the size the live proof sends -- is NOT enough here:
#: on loopback it lands in the buffer whole and the race never happens.
PAYLOAD = b"x" * (512 * 1024)

#: Set on the listener BEFORE `listen`, so the accepted socket inherits it. This
#: plus a server that never reads the body is what blocks the client's write.
RECEIVE_BUFFER_BYTES = 1024


def _serve(behaviour: str) -> tuple[str, int, threading.Thread]:
    """One connection, served the chosen way, on a port the OS picks."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RECEIVE_BUFFER_BYTES)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    host, port = listener.getsockname()

    def run() -> None:
        try:
            connection, _ = listener.accept()
        except OSError:
            return
        try:
            connection.settimeout(10)
            # ONLY the headers. Leaving the body unread is the point: it closes
            # the client's window and blocks its write, which is the condition
            # the defect needs and the first version of this file lacked.
            head = b""
            while b"\r\n\r\n" not in head and len(head) < 65536:
                chunk = connection.recv(256)
                if not chunk:
                    break
                head += chunk

            if behaviour == "answer_then_rst":
                connection.sendall(REFUSAL)
                # SO_LINGER with a zero timeout makes close() send RST rather
                # than FIN. This is the host's ECONNRESET arm, and the harsh
                # case: an RST can discard whatever the peer has not yet read.
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            elif behaviour == "answer_then_fin":
                connection.sendall(REFUSAL)
                connection.shutdown(socket.SHUT_WR)
            elif behaviour == "silent_rst":
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            else:  # pragma: no cover - a typo in an arm name must not pass quietly
                raise AssertionError(f"unknown behaviour {behaviour!r}")
        except OSError:
            pass
        finally:
            try:
                connection.close()
            except OSError:
                pass
            listener.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return host, port, thread


def _urllib_status(url: str, payload: bytes) -> int:
    """What `api_call` does today: urllib, one write, one read."""
    request = urllib.request.Request(url, data=payload, method="POST")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


@pytest.mark.parametrize("behaviour", ["answer_then_rst", "answer_then_fin"])
def test_the_refusal_survives_a_connection_broken_mid_write(behaviour: str) -> None:
    """413 in both arms the host produced: ECONNRESET and EPIPE."""
    host, port, thread = _serve(behaviour)
    refusal = post_and_read_refusal(f"http://{host}:{port}/auth/login", PAYLOAD)
    thread.join(timeout=15)

    assert refusal.status == 413, (
        f"[{behaviour}] the server sent a 413 and the client reported "
        f"{refusal.status}: {refusal.reason}"
    )
    assert not refusal.wrote_whole_body, (
        "the client sent the entire body although the server had already answered; "
        "the rig is not producing the blocked-write condition and neither arm is evidence"
    )


@pytest.mark.parametrize("behaviour", ["answer_then_rst", "answer_then_fin"])
def test_the_current_client_loses_that_refusal(behaviour: str) -> None:
    """The premise, asserted rather than assumed.

    Without this the arms above could pass against a rig that reproduces no
    defect at all -- which is precisely what the first version of this file did,
    green and worthless. Here `urllib` is driven through the same servers and
    must come back with **0**, which is the failure seen on the host.

    **If this ever goes red, the repair may be retirable** rather than broken:
    it would mean urllib had learned to recover a response after a failed write,
    and `tests/deployment/oversized_request.py` would exist for nothing. Read it
    that way round before assuming a regression.
    """
    host, port, thread = _serve(behaviour)
    status = _urllib_status(f"http://{host}:{port}/auth/login", PAYLOAD)
    thread.join(timeout=15)

    assert status == 0, (
        f"[{behaviour}] urllib recovered status {status}, so this rig is not "
        "reproducing D511 and the arms above prove nothing about the repair"
    )


def test_a_server_that_answers_nothing_is_not_reported_as_a_refusal() -> None:
    """The arm that keeps the repair honest (D509).

    A connection that broke with nothing received must NOT come back as 413.
    Otherwise "tolerates a broken pipe" and "recovers the response" look
    identical, and the live proof would go green for the defect it exists to
    detect: a buffering middleware that is not attached.
    """
    host, port, thread = _serve("silent_rst")
    refusal = post_and_read_refusal(f"http://{host}:{port}/auth/login", PAYLOAD)
    thread.join(timeout=15)

    assert refusal.status != 413, "a server that said nothing was reported as refusing"
    assert refusal.status == 0, (
        f"expected 0 for a server that answered nothing, got {refusal.status}: {refusal.reason}"
    )
    assert refusal.reason, "status 0 must carry a reason; that is the whole point of the field"
