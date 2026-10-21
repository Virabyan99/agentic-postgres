"""The SQL relay (Session 44, ADR 0286): a WebSocket in, a project's door out.

The console's editor (ADR 0285) speaks PostgreSQL's protocol from the browser,
which can open a WebSocket and nothing else. This process turns one WebSocket
into one TLS connection to a project's public door -- through the edge's own
Postgres entrypoint, by the name the certificate proves -- and carries bytes
both ways. **It authenticates nothing and holds nothing**: no secret, no mount,
no call to `/v1`. The door is already public (ADR 0268), so what it must not
become is a way to reach anything else, a free pool of sockets, or a recorder.

Admission, in this order, before any TCP (D2762 -- the library's own `origins`
check would run after `process_request`, so the relay does it itself):

1. `Origin` byte-for-byte the console's, else HTTP 403;
2. the one path, `/v1/door/<host>`, `<host>` in the door grammar `naming`
   derives (D2740), else HTTP 400;
3. the ceilings -- after the upgrade, so the page can say why: close 4429.

Upstream: the edge's alias and postgres entrypoint, rendered (never typed);
SSLRequest, `S`, then TLS >= 1.2 with SNI = the door host, ALPN `postgresql`,
the certificate verified against the image's system trust store (D2739). The
door host is used only as SNI, never looked up. Any failure there closes 4502
*could not reach the database* -- never *asleep* (ADR 0195; ADR 0268 :68,73).

**One line per session on stdout, and nothing else** (D2743). The library's
loggers are given a handler that writes nothing; every exception in a session
is caught here and no exception text is ever printed.

Standard library and `websockets` only. Read once at start, each refusing to
start when missing or malformed: `APG_SQL_RELAY_PORT`,
`APG_SQL_RELAY_ALLOWED_ORIGIN`, `APG_SQL_RELAY_ZONE`, `APG_SQL_RELAY_UPSTREAM`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import ssl
import struct
import sys
import time
from collections.abc import Callable, Mapping
from typing import NamedTuple

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

# ADR 0286 decision 5: every bound one constant, each held by a test.
MAX_SESSIONS = 32
MAX_SESSIONS_PER_DOOR = 4
MAX_SESSIONS_PER_SOURCE = 4
IDLE_SECONDS = 300.0
TOTAL_SECONDS = 1800.0
MAX_MESSAGE_BYTES = 1 << 20
MAX_DOWN_BYTES = 64 << 20
MAX_PENDING_BYTES = 64 << 10
CHUNK_BYTES = 64 << 10
PING_SECONDS = 20.0
CONNECT_SECONDS = 10.0
TICK_SECONDS = 1.0

CLOSE_TEXT_FRAME = 4400
CLOSE_TIME = 4408
CLOSE_TOO_MUCH = 4413
CLOSE_CEILING = 4429
CLOSE_UNREACHABLE = 4502

PATH_PREFIX = "/v1/door/"
HEALTH_PATH = "/__apg/healthz"
SSL_REQUEST = struct.pack("!ii", 8, 80877103)

_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_DOMAIN = re.compile(rf"(?:{_LABEL}\.)+{_LABEL}")
_ORIGIN = re.compile(rf"https://{_DOMAIN.pattern}")
_UPSTREAM = re.compile(rf"({_LABEL}(?:\.{_LABEL})*):([0-9]{{1,5}})")
MAX_HOST_LENGTH = 253

# The library's loggers: a handler that writes nothing, and no propagation to
# Python's last-resort stderr handler (rig 44d: `websockets` logs a handler's
# traceback by itself, D2762).
QUIET = logging.getLogger("apg-sql-relay.quiet")
for _name in ("apg-sql-relay.quiet", "websockets", "asyncio"):
    _logger = logging.getLogger(_name)
    _logger.addHandler(logging.NullHandler())
    _logger.propagate = False


class Configuration(NamedTuple):
    port: int
    allowed_origin: str
    zone: str
    upstream_host: str
    upstream_port: int


class Refused(ValueError):
    """The environment is missing a value or holds a malformed one."""


def configuration(environ: Mapping[str, str]) -> Configuration:
    """The four values, each validated; anything else refuses to start."""

    def value(name: str) -> str:
        found = environ.get(name, "")
        if not found:
            raise Refused(f"{name} is not set")
        return found

    port_text = value("APG_SQL_RELAY_PORT")
    if not port_text.isdigit() or not 0 < int(port_text) < 65536:
        raise Refused("APG_SQL_RELAY_PORT is not a port")
    origin = value("APG_SQL_RELAY_ALLOWED_ORIGIN")
    if not _ORIGIN.fullmatch(origin):
        raise Refused("APG_SQL_RELAY_ALLOWED_ORIGIN is not exactly https://<host>")
    zone = value("APG_SQL_RELAY_ZONE")
    if not _DOMAIN.fullmatch(zone) or len(zone) > MAX_HOST_LENGTH:
        raise Refused("APG_SQL_RELAY_ZONE is not a domain of two labels or more")
    upstream = _UPSTREAM.fullmatch(value("APG_SQL_RELAY_UPSTREAM"))
    if not upstream or not 0 < int(upstream.group(2)) < 65536:
        raise Refused("APG_SQL_RELAY_UPSTREAM is not host:port")
    return Configuration(int(port_text), origin, zone, upstream.group(1), int(upstream.group(2)))


def door_pattern(zone: str) -> re.Pattern[str]:
    """D2740: `[<branch>.](pool|direct).<slot>.<zone>` -- the names `naming`
    derives for a door (`endpoint_hosts`, `branch_endpoint_hosts`), and nothing
    else: no address, no port, no other label count, no uppercase."""
    return re.compile(rf"(?:{_LABEL}\.)?(?:pool|direct)\.{_LABEL}\.{re.escape(zone)}")


def door_context() -> ssl.SSLContext:
    """D2739: the image's system trust store, TLS >= 1.2, ALPN `postgresql`,
    the hostname checked. There is deliberately no way to pass a CA here."""
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(["postgresql"])
    return context


class Close(Exception):
    def __init__(self, code: int, reason: str, outcome: str) -> None:
        super().__init__(code)
        self.code = code
        self.reason = reason
        self.outcome = outcome


class Relay:
    def __init__(
        self,
        config: Configuration,
        *,
        log: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.log = log or (lambda line: print(line, flush=True))
        self.clock = clock
        self.doors = door_pattern(config.zone)
        self.context = door_context()
        self.total = 0
        self.per_door: dict[str, int] = {}
        self.per_source: dict[str, int] = {}

    # -- admission -----------------------------------------------------------

    def process_request(self, connection: ServerConnection, request: Request) -> Response | None:
        if request.path == HEALTH_PATH:
            return connection.respond(200, '{"status":"ok"}\n')
        if request.headers.get("Origin") != self.config.allowed_origin:
            self.log("apg-sql-relay refused reason=origin")
            return connection.respond(403, "Forbidden\n")
        door = request.path[len(PATH_PREFIX) :] if request.path.startswith(PATH_PREFIX) else ""
        if len(door) > MAX_HOST_LENGTH or not self.doors.fullmatch(door):
            self.log("apg-sql-relay refused reason=path")
            return connection.respond(400, "Bad Request\n")
        return None

    def _source(self, connection: ServerConnection) -> str:
        # The edge overwrites X-Real-Ip with the true peer (rig 44a, D2764).
        forwarded = connection.request.headers.get("X-Real-Ip") if connection.request else None
        if forwarded:
            return forwarded
        address = connection.remote_address
        return str(address[0]) if address else "-"

    def _admit(self, door: str, source: str) -> bool:
        if (
            self.total >= MAX_SESSIONS
            or self.per_door.get(door, 0) >= MAX_SESSIONS_PER_DOOR
            or self.per_source.get(source, 0) >= MAX_SESSIONS_PER_SOURCE
        ):
            return False
        self.total += 1
        self.per_door[door] = self.per_door.get(door, 0) + 1
        self.per_source[source] = self.per_source.get(source, 0) + 1
        return True

    def _release(self, door: str, source: str) -> None:
        self.total -= 1
        for table, key in ((self.per_door, door), (self.per_source, source)):
            table[key] -= 1
            if not table[key]:
                del table[key]

    # -- a session -----------------------------------------------------------

    async def _open_door(self, door: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.config.upstream_host, self.config.upstream_port),
            CONNECT_SECONDS,
        )
        try:
            writer.write(SSL_REQUEST)
            await writer.drain()
            answer = await asyncio.wait_for(reader.readexactly(1), CONNECT_SECONDS)
            if answer != b"S":
                raise ConnectionError("no TLS")
            await asyncio.wait_for(
                writer.start_tls(self.context, server_hostname=door), CONNECT_SECONDS
            )
        except BaseException:
            writer.close()
            raise
        return reader, writer

    async def handler(self, websocket: ServerConnection) -> None:
        door = websocket.request.path[len(PATH_PREFIX) :]
        source = self._source(websocket)
        session = secrets.token_hex(8)
        started = self.clock()
        counts = {"up": 0, "down": 0}
        if not self._admit(door, source):
            await websocket.close(CLOSE_CEILING, "too many sessions")
            outcome, code = "refused", CLOSE_CEILING
        else:
            try:
                outcome, code = await self._carry(websocket, door, counts)
            except Exception:
                outcome, code = "closed", 1011
                await websocket.close(1011, "the relay failed")
            finally:
                self._release(door, source)
        self.log(
            f"apg-sql-relay session={session} door={door} outcome={outcome} code={code} "
            f"seconds={self.clock() - started:.1f} up={counts['up']} down={counts['down']}"
        )

    async def _carry(
        self, websocket: ServerConnection, door: str, counts: dict[str, int]
    ) -> tuple[str, int]:
        started = self.clock()
        last = [started]
        pending = bytearray()
        ready = asyncio.Event()
        streams: dict[str, asyncio.StreamWriter] = {}

        async def from_browser() -> None:
            async for message in websocket:
                if isinstance(message, str):
                    raise Close(CLOSE_TEXT_FRAME, "the protocol is bytes", "closed")
                last[0] = self.clock()
                counts["up"] += len(message)
                if not ready.is_set():
                    pending.extend(message)
                    if len(pending) > MAX_PENDING_BYTES:
                        raise Close(CLOSE_TOO_MUCH, "too much before the database", "closed")
                    continue
                streams["writer"].write(message)
                await streams["writer"].drain()
            raise Close(websocket.close_code or 1000, "", "closed")

        async def to_browser() -> None:
            try:
                reader, writer = await self._open_door(door)
            except (OSError, ssl.SSLError, asyncio.IncompleteReadError, TimeoutError):
                raise Close(
                    CLOSE_UNREACHABLE, "could not reach the database", "unreachable"
                ) from None
            streams["writer"] = writer
            if pending:
                writer.write(bytes(pending))
                pending.clear()
                await writer.drain()
            ready.set()
            while chunk := await reader.read(CHUNK_BYTES):
                last[0] = self.clock()
                counts["down"] += len(chunk)
                if counts["down"] > MAX_DOWN_BYTES:
                    raise Close(CLOSE_TOO_MUCH, "too much for one session", "closed")
                await websocket.send(chunk)
            raise Close(1000, "the database closed the session", "closed")

        async def timer() -> None:
            while True:
                await asyncio.sleep(TICK_SECONDS)
                now = self.clock()
                if now - started >= TOTAL_SECONDS:
                    raise Close(CLOSE_TIME, "the session's time is up", "closed")
                if now - last[0] >= IDLE_SECONDS:
                    raise Close(CLOSE_TIME, "idle", "closed")

        tasks = [asyncio.ensure_future(f()) for f in (from_browser, to_browser, timer)]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if "writer" in streams:
                streams["writer"].close()
        failures = [task.exception() for task in done if not task.cancelled()]
        failure = next(
            (f for f in failures if isinstance(f, Close)), failures[0] if failures else None
        )
        if isinstance(failure, Close):
            close = failure
        elif isinstance(failure, ConnectionClosed):
            # The browser went away, or the library closed it (1009 for a message
            # over MAX_MESSAGE_BYTES): the code is whatever was exchanged.
            close = Close(websocket.close_code or 1006, "", "closed")
        else:
            close = Close(1011, "the relay failed", "closed")
        await websocket.close(close.code, close.reason)
        return close.outcome, close.code

    async def serve(self, host: str, port: int):
        return await serve(
            self.handler,
            host,
            port,
            process_request=self.process_request,
            max_size=MAX_MESSAGE_BYTES,
            max_queue=2,
            ping_interval=PING_SECONDS,
            ping_timeout=PING_SECONDS,
            compression=None,
            server_header=None,
            logger=QUIET,
        )


async def _run(config: Configuration) -> None:
    server = await Relay(config).serve("0.0.0.0", config.port)  # noqa: S104 -- inside its container
    await server.serve_forever()


def main() -> int:
    try:
        config = configuration(os.environ)
    except Refused as refused:
        print(f"apg-sql-relay refused to start: {refused}", file=sys.stderr, flush=True)
        return 2
    asyncio.run(_run(config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
