"""A client that does not lose a refusal the server sent while it was writing.

**D511.** `test_the_published_route_applies_the_input_bounds_before_the_service_-
allocates` sends a 64 KiB body and asserts the edge answers **413**. Traefik's
buffering middleware refuses on `Content-Length` and closes the connection
immediately — *while the client is still writing the body*. `urllib` then raises
`BrokenPipeError` or `ConnectionResetError` and **discards the response it had
already received**, so the proof reports status `0` and fails on a deployment
that is behaving exactly as designed.

Measured across one host trip at a single release: `ECONNRESET`, then `EPIPE`,
then a pass. Three runs, three outcomes, nothing changed between them.

**What this is not.** Treating a broken pipe *as success* is refused — it would
go green whenever the connection broke, **including for the defect the proof
exists to detect** (D509: a control that cannot fail for the reason it is
watching for is not a control). This never invents a status. If the server sent
no response, :func:`post_and_read_refusal` returns status ``0`` and the
assertion fails exactly as it does today.

**How the race is won instead of tolerated.** The body is written in small
chunks, and before each chunk the socket is checked for readability. The moment
the server has answered, writing stops and the response is read. The connection
is therefore usually still open when the response is taken, which matters
because a server that gives up on a client still writing may send **RST** — and
an RST discards the receive buffer, taking the response with it. Reading early
avoids the case that a write-then-recover client cannot handle.

A write error is still tolerated *as a signal to stop writing*, not as an
outcome: the read is attempted afterwards regardless, and whatever it finds --
including nothing -- is what gets reported.
"""

from __future__ import annotations

import select
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urlsplit

#: Small enough that the readability check happens often during a 64 KiB body,
#: large enough not to turn one request into thousands of syscalls.
CHUNK_BYTES = 4096

#: How long to wait for a response once writing has stopped.
READ_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Refusal:
    """What the server said, or why nothing was heard.

    ``status`` is ``0`` when no response was read at all — the same convention
    `api_call`'s ``ApiResponse`` uses, and for the same reason: "it refused" and
    "it was not there" are different findings and an assertion that only looks
    for the absence of a 200 cannot tell them apart.
    """

    status: int
    reason: str = ""
    wrote_whole_body: bool = False


def _readable(sock: socket.socket) -> bool:
    """Whether a response is already waiting.

    `select` alone is not enough on a TLS socket: bytes can sit in the SSL
    object's own buffer with nothing left at the file descriptor, and `select`
    reports not-readable while `recv` would return data immediately.
    """
    if isinstance(sock, ssl.SSLSocket) and sock.pending():
        return True
    return bool(select.select([sock], [], [], 0)[0])


def _request_bytes(
    method: str, path: str, host: str, headers: dict[str, str], length: int
) -> bytes:
    lines = [f"{method} {path} HTTP/1.1", f"Host: {host}", f"Content-Length: {length}"]
    lines += [f"{name}: {value}" for name, value in headers.items()]
    # No keep-alive: this connection is used once and the server is expected to
    # close it. Asking for `close` makes the end of the body unambiguous.
    lines += ["Connection: close", "", ""]
    return "\r\n".join(lines).encode("ascii")


def _read_status(sock: socket.socket) -> tuple[int, str]:
    """The status line of whatever the server sent, or (0, why not)."""
    sock.settimeout(READ_TIMEOUT_SECONDS)
    buffer = b""
    try:
        while b"\r\n" not in buffer and len(buffer) < 8192:
            received = sock.recv(CHUNK_BYTES)
            if not received:
                break
            buffer += received
    except (TimeoutError, OSError) as error:
        if not buffer:
            return 0, f"{type(error).__name__}: {error}"

    if not buffer:
        return 0, "the server closed without sending a response"

    first = buffer.split(b"\r\n", 1)[0].decode("latin-1")
    parts = first.split(" ", 2)
    if len(parts) < 2 or not parts[1].isdigit():
        return 0, f"unparseable status line: {first!r}"
    return int(parts[1]), first


def post_and_read_refusal(
    url: str,
    payload: bytes,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> Refusal:
    """POST ``payload``, stop writing as soon as the server answers, report it.

    Returns a :class:`Refusal` with the status the server actually sent. It
    never synthesises one: a connection that broke with nothing received is
    ``status=0``, which fails the caller's assertion.
    """
    split = urlsplit(url)
    secure = split.scheme == "https"
    host = split.hostname or ""
    port = split.port or (443 if secure else 80)
    path = split.path or "/"
    if split.query:
        path = f"{path}?{split.query}"

    sock = socket.create_connection((host, port), timeout=timeout)
    try:
        if secure:
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)

        sock.sendall(_request_bytes("POST", path, split.netloc, headers or {}, len(payload)))

        wrote_whole_body = True
        write_note = ""
        for start in range(0, len(payload), CHUNK_BYTES):
            if _readable(sock):
                # The server has already refused. Stop writing: continuing is
                # what provokes the RST that would discard its answer.
                wrote_whole_body = False
                write_note = "the server answered before the body was fully sent"
                break
            try:
                sock.sendall(payload[start : start + CHUNK_BYTES])
            except OSError as error:
                # A signal to stop writing, never an outcome. The read below
                # decides what happened.
                wrote_whole_body = False
                write_note = f"{type(error).__name__} while writing: {error}"
                break

        status, line = _read_status(sock)
        reason = line if not write_note else f"{line} ({write_note})"
        return Refusal(status=status, reason=reason, wrote_whole_body=wrote_whole_body)
    finally:
        try:
            sock.close()
        except OSError:
            pass
