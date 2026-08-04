"""Classifying listening sockets by whether anything off the host can reach them.

The two fixtures below are real ``ss`` output from the Session 2 deployment host
before provisioning. They are here because the defect this module fixes was only
visible on a real machine: the check read port numbers and discarded bind
addresses, so ``systemd-resolved``'s loopback stub on ``127.0.0.53:53`` was
reported as an exposed port. A check that cries wolf on a default Ubuntu
installation is a check operators learn to skip.

Every test here is paired. It is not enough to prove loopback is ignored — that
is the easy half, and getting it too enthusiastically right means ``0.0.0.0``
gets ignored too, which is the failure that matters. So each exclusion is
asserted alongside the inclusion it must not swallow.
"""

from __future__ import annotations

import pytest

from agentic_postgres.listeners import parse_listeners, unexpected_public_ports

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

# Verbatim TCP rows from the deployment host, pre-provisioning. This is what
# `provision-host.sh` actually pipes in: `ss -H -lnt`.
HOST_SS_TCP = """\
tcp   LISTEN 0      4096        127.0.0.53%lo:53        0.0.0.0:*
tcp   LISTEN 0      4096           127.0.0.54:53        0.0.0.0:*
tcp   LISTEN 0      4096              0.0.0.0:22        0.0.0.0:*
tcp   LISTEN 0      4096                 [::]:22           [::]:*
"""

# The same host's full `ss -lntu`, UDP included, kept so the TCP scoping above
# is a stated choice rather than an accident nobody wrote down.
HOST_SS_ALL = (
    """\
udp   UNCONN 0      0              127.0.0.54:53        0.0.0.0:*
udp   UNCONN 0      0           127.0.0.53%lo:53        0.0.0.0:*
udp   UNCONN 0      0      62.238.99.122%eth0:68        0.0.0.0:*
udp   UNCONN 0      0               127.0.0.1:323       0.0.0.0:*
udp   UNCONN 0      0                   [::1]:323          [::]:*
"""
    + HOST_SS_TCP
)

BASELINE_PORTS = (22, 80, 443)


def test_the_real_host_reports_nothing_unexpected() -> None:
    """The state that produced a spurious DEVIATE must now be clean."""
    assert unexpected_public_ports(HOST_SS_TCP, BASELINE_PORTS) == ()


def test_the_baseline_reads_tcp_and_that_is_a_choice() -> None:
    """The DHCP client really does bind UDP/68 on the public address.

    It is not loopback and this module does not pretend otherwise — feed it the
    UDP rows and it reports the port. The baseline check passes only TCP because
    the reachability being asserted is PostgreSQL's, and PostgreSQL is TCP. If
    that scope ever widens, port 68 is the first thing that has to be decided
    about, and this test is where that shows up rather than in a surprise on a
    host.
    """
    assert unexpected_public_ports(HOST_SS_ALL, BASELINE_PORTS) == (68,)


def test_protocol_is_captured_when_ss_reports_it() -> None:
    """The live host check allows udp/68 by name, which needs the protocol.

    A port-only allowance for 68 would also permit a TCP listener on 68, which
    is not what the DHCP client does and not what was decided.
    """
    by_key = {
        (listener.protocol, listener.port): listener for listener in parse_listeners(HOST_SS_ALL)
    }
    assert ("udp", 68) in by_key
    assert ("tcp", 22) in by_key
    assert ("tcp", 68) not in by_key


def test_the_dns_stub_is_recognised_as_loopback_but_dhcp_is_not() -> None:
    """Both are 'not 22/80/443'. Only one of them is unreachable from outside."""
    by_port = {listener.port: listener for listener in parse_listeners(HOST_SS_ALL)}
    assert by_port[53].is_loopback is True
    assert by_port[68].is_loopback is False


@pytest.mark.parametrize(
    ("endpoint", "expected_loopback"),
    [
        ("127.0.0.1:5432", True),
        ("127.0.0.53%lo:5432", True),
        ("[::1]:5432", True),
        ("127.255.255.254:5432", True),  # all of 127/8, not just 127.0.0.1
        ("0.0.0.0:5432", False),
        ("[::]:5432", False),
        ("*:5432", False),
        ("62.238.99.122:5432", False),
        ("10.0.0.5:5432", False),  # private is not loopback
        ("[fe80::1%eth0]:5432", False),  # link-local is not loopback
    ],
)
def test_bind_address_classification(endpoint: str, expected_loopback: bool) -> None:
    line = f"tcp   LISTEN 0      4096 {endpoint} 0.0.0.0:*"
    (listener,) = parse_listeners(line)
    assert listener.port == 5432
    assert listener.is_loopback is expected_loopback


@pytest.mark.parametrize(
    "endpoint",
    ["0.0.0.0:5432", "[::]:5432", "*:5432", "62.238.99.122:5432", "10.0.0.5:5432"],
)
def test_a_publicly_bound_database_port_is_always_reported(endpoint: str) -> None:
    """The whole point. Every non-loopback bind of 5432 must be visible."""
    line = f"tcp   LISTEN 0      4096 {endpoint} 0.0.0.0:*"
    assert unexpected_public_ports(line, BASELINE_PORTS) == (5432,)


def test_a_loopback_database_port_is_not_reported() -> None:
    """The other direction, so the test above cannot pass by reporting everything."""
    line = "tcp   LISTEN 0      4096 127.0.0.1:5432 0.0.0.0:*"
    assert unexpected_public_ports(line, BASELINE_PORTS) == ()


def test_an_unparseable_address_counts_as_exposed() -> None:
    """Unknown shape means unknown reachability, and the safe answer is 'exposed'."""
    line = "tcp   LISTEN 0      4096 not-an-address:5432 0.0.0.0:*"
    assert unexpected_public_ports(line, BASELINE_PORTS) == (5432,)


def test_both_ss_column_layouts_parse_to_the_same_answer() -> None:
    """`ss -lnt` omits the Netid column that `ss -lntu` prints.

    Reading a fixed column index gets one of these right and silently parses a
    queue depth as an address in the other. That is not hypothetical — it is the
    bug this test was written after hitting.
    """
    with_netid = "tcp   LISTEN 0      4096              0.0.0.0:5432        0.0.0.0:*"
    without_netid = "LISTEN 0      4096              0.0.0.0:5432        0.0.0.0:*"

    (a,), (b,) = parse_listeners(with_netid), parse_listeners(without_netid)
    assert (a.address, a.port, a.is_loopback) == (b.address, b.port, b.is_loopback)
    assert unexpected_public_ports(without_netid, BASELINE_PORTS) == (5432,)

    # Protocol is the one field that legitimately differs, and it must be None
    # rather than a guess: inventing "tcp" for a row that did not say so would
    # let a UDP allowance quietly cover a TCP listener.
    assert a.protocol == "tcp"
    assert b.protocol is None


def test_a_queue_depth_is_never_mistaken_for_an_address() -> None:
    """The guard on the test above: a bare number must not become a listener."""
    assert parse_listeners("LISTEN 0 4096") == ()


def test_a_header_line_does_not_become_a_listener() -> None:
    """`ss` without -H, or a version that adds a column, must not crash the check."""
    output = "Netid State  Recv-Q Send-Q Local Address:Port Peer Address:Port\n" + HOST_SS_TCP
    assert unexpected_public_ports(output, BASELINE_PORTS) == ()


def test_ports_are_reported_once_and_sorted() -> None:
    output = "\n".join(
        [
            "tcp   LISTEN 0 4096 0.0.0.0:9000 0.0.0.0:*",
            "tcp   LISTEN 0 4096 [::]:9000 [::]:*",
            "tcp   LISTEN 0 4096 0.0.0.0:5432 0.0.0.0:*",
        ]
    )
    assert unexpected_public_ports(output, BASELINE_PORTS) == (5432, 9000)
