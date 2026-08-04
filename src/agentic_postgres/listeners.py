"""Which listening sockets on a host are reachable from off the host.

``bin/provision-host.sh --check`` asserts that nothing is listening except SSH,
80 and 443. That claim is only meaningful if "listening" means "reachable" —
and on Ubuntu it does not, because ``systemd-resolved`` binds a DNS stub to
``127.0.0.53`` on every installation. A check that reads a port number and
discards the address it was bound to reports that stub as an exposure, which is
wrong in the direction that trains an operator to ignore the check.

The rule here is the one the requirement actually cares about:

    A socket bound to a loopback address cannot receive a packet that arrived on
    a public interface. A socket bound to anything else can.

So ``127.0.0.53:53`` and ``[::1]:323`` are invisible from outside and do not
count, while ``0.0.0.0``, ``::``, ``*`` and *any* named address — including
private and link-local ones — do. The failure to avoid is the mirror of the one
above: treating ``0.0.0.0:5432`` as harmless because a wildcard "isn't a real
address". A wildcard binds every interface the host has, which is the most
exposed thing a socket can be.

This decides nothing on its own. SEC-NET-001 is proved by a full-TCP connect
scan run from a different network, which observes reachability rather than
inferring it. This is the host-local half that says *why* when that scan finds
something, and catches a regression before the external run is even set up.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass

__all__ = ["Listener", "parse_listeners", "unexpected_public_ports"]


@dataclass(frozen=True)
class Listener:
    """One listening socket, as ``ss`` reported it."""

    address: str
    port: int
    is_loopback: bool


def _split_host_port(endpoint: str) -> tuple[str, int] | None:
    """Split an ``ss`` local-address field into an address and a port.

    ``ss`` writes ``127.0.0.53%lo:53``, ``0.0.0.0:22``, ``[::]:22`` and
    ``[fe80::1%eth0]:53``. The zone suffix is display detail, and the port is
    always after the *last* colon, which is the only reason an IPv6 address can
    be split this way at all.
    """
    endpoint = endpoint.strip()
    if not endpoint or ":" not in endpoint:
        return None
    address, _, port_text = endpoint.rpartition(":")
    if not port_text.isdigit():
        return None
    address = address.strip("[]")
    address, _, _zone = address.partition("%")
    return address, int(port_text)


def _is_loopback(address: str) -> bool:
    """True only for addresses no off-host packet can be delivered to.

    A wildcard is emphatically not loopback: it binds every interface. An
    address this function cannot parse is reported as non-loopback, because the
    safe answer to "is this exposed" is yes.
    """
    if address in {"*", "0.0.0.0", "::", ""}:  # noqa: S104 -- classifying, not binding
        return False
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def parse_listeners(ss_output: str) -> tuple[Listener, ...]:
    """Parse the output of ``ss -H -lnt`` (or ``-lntu``) into listeners.

    The local address is found by *shape*, not by column index. ``ss -lnt``
    omits the ``Netid`` column that ``ss -lntu`` prints, so the local address is
    field 4 under one flag set and field 5 under the other — reading a fixed
    index silently parses a queue depth as an address the first time someone
    adds ``u``.

    The first field that is an ``address:port`` with a numeric port is the local
    address. Nothing earlier on the line can match: the state and protocol
    columns are words, and the queue depths have no colon. The peer column
    cannot match either, because for a listening socket its port is ``*``.

    Lines with no such field are skipped rather than raising. ``ss`` output
    varies across versions and a stray header must not turn a policy check into
    a crash.
    """
    listeners: list[Listener] = []
    for line in ss_output.splitlines():
        for field in line.split():
            parsed = _split_host_port(field)
            if parsed is None:
                continue
            address, port = parsed
            listeners.append(
                Listener(address=address, port=port, is_loopback=_is_loopback(address))
            )
            break
    return tuple(listeners)


def unexpected_public_ports(ss_output: str, allowed_ports: Iterable[int]) -> tuple[int, ...]:
    """Public listening ports that are not in ``allowed_ports``, sorted.

    Loopback-bound sockets are excluded entirely. Everything else that is not
    explicitly permitted is reported.
    """
    permitted = {int(port) for port in allowed_ports}
    unexpected = {
        listener.port
        for listener in parse_listeners(ss_output)
        if not listener.is_loopback and listener.port not in permitted
    }
    return tuple(sorted(unexpected))
