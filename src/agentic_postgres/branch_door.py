"""Is a branch's door open: both its names verified through the edge (Session 41, D2515, ADR 0271).

Session 40 wrote a branch `ready` the moment the edge had attached its
network, and the names answered ~4.5 s later, once the edge's certificate for
them was issued (D2503): `ready` named a state a customer could not reach. This
reads the door the way a customer's client meets it -- PostgreSQL's
`SSLRequest` to the edge's postgres entrypoint, then TLS with the branch name
as SNI and ALPN `postgresql`, the chain verified against the system store and
the name -- and the runtime writes `ready` only after both names verify, or says
`door: pending` with the reason when the bound runs out.

**Three outcomes** (ADR 0195), as rig 41b and the host measured them (D2537):

- `ready` -- the handshake verified for the name.
- `pending` -- the edge answered the `SSLRequest` with `S` and the name did not
  verify: a certificate that does not verify **or an EOF in the handshake**,
  which is what Traefik's `sniStrict` gives a name it holds no certificate for
  (it serves no default certificate). A name with no router gives the same EOF,
  so `pending` at the bound says both.
- `unknown` -- the check could not run: no connection, no `S`, or any other TLS
  failure.
"""

from __future__ import annotations

import socket
import ssl
import struct
import time
from collections.abc import Callable, Iterable
from typing import Any

__all__ = [
    "DOOR_INTERVAL_SECONDS",
    "DOOR_SECONDS",
    "EDGE_ADDRESS",
    "SSL_REQUEST",
    "check",
    "client_context",
    "wait",
]

#: PostgreSQL's SSLRequest: length 8, code 80877103.
SSL_REQUEST = struct.pack("!ii", 8, 80877103)
#: The edge's postgres entrypoint as the host reaches it (ADR 0268).
EDGE_ADDRESS = ("127.0.0.1", 5432)
#: How long `ready` waits for the door, and how often it asks. Rig 41b: both
#: names verified 3.0 s after their routers existed; Session 40's trip: 4.5 s
#: after `ready` (D2503). 180 s is the bound the plan set against them.
DOOR_SECONDS = 180
DOOR_INTERVAL_SECONDS = 5
_HANDSHAKE_SECONDS = 5.0


def client_context() -> ssl.SSLContext:
    """A client context that verifies the chain against the system store AND the
    name, offering ALPN `postgresql` (libpq 18 refuses otherwise, Session 39)."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_default_certs()
    context.set_alpn_protocols(["postgresql"])
    return context


def check(
    host: str,
    *,
    context: ssl.SSLContext,
    address: tuple[str, int] = EDGE_ADDRESS,
    connect: Callable[..., Any] = socket.create_connection,
    timeout: float = _HANDSHAKE_SECONDS,
) -> tuple[str, str]:
    """`(state, reason)` for one name: `ready` / `pending` / `unknown`."""
    try:
        raw = connect(address, timeout=timeout)
    except OSError as error:
        return "unknown", f"the edge did not accept a connection: {error}"
    try:
        raw.sendall(SSL_REQUEST)
        answer = raw.recv(1)
        if answer != b"S":
            return "unknown", f"the edge answered the SSLRequest with {answer!r}, not 'S'"
        with context.wrap_socket(raw, server_hostname=host):
            return "ready", ""
    except ssl.SSLCertVerificationError as error:
        return "pending", f"{host}'s certificate does not verify yet: {error.verify_message}"
    except ssl.SSLEOFError:
        return "pending", f"the edge holds no certificate for {host} yet"
    except (ssl.SSLError, OSError) as error:
        return "unknown", f"the TLS handshake with {host} failed: {error}"
    finally:
        raw.close()


def wait(
    hosts: Iterable[str],
    *,
    probe: Callable[[str], tuple[str, str]],
    seconds: float = DOOR_SECONDS,
    interval: float = DOOR_INTERVAL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, str | None]:
    """`("ready", None)` once every name verified; at the bound, the door's state
    and the reason of the first name that did not -- `pending` when the edge
    answered for every name that is not ready, `unknown` when any check could
    not run."""
    names = list(hosts)
    deadline = clock() + seconds
    while True:
        outcomes = {name: probe(name) for name in names}
        if all(state == "ready" for state, _ in outcomes.values()):
            return "ready", None
        if clock() >= deadline:
            open_not = {n: o for n, o in outcomes.items() if o[0] != "ready"}
            door = "unknown" if any(s == "unknown" for s, _ in open_not.values()) else "pending"
            reasons = "; ".join(reason for _, reason in open_not.values())
            return door, f"the door is not open after {int(seconds)} s: {reasons}"
        sleep(interval)
