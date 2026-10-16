"""`ready` means the door answers (Session 41, D2503, D2515, D2537, ADR 0271).

`agentic_postgres.branch_door` reads a branch's two names the way a client
meets them -- the SSLRequest, then TLS with SNI and ALPN, the chain and the name
verified -- and classifies what it read into three outcomes. The outcomes are
the ones rig 41b and the host measured (D2537): before the edge holds a
certificate for a name, Traefik's `sniStrict` closes the handshake (an EOF, no
default certificate), exactly as for a name with no router; a certificate that
does not verify is the other `pending`; only a check that could not run is
`unknown`. The runtime's ordering -- `ready` written only after the door -- is
`test_branch_runtime.py::test_the_poolers_start_after_the_rekey`'s.
"""

from __future__ import annotations

import ssl
from typing import Any

import pytest

from agentic_postgres import branch_door

pytestmark = [pytest.mark.contract, pytest.mark.p0]

POOL = "dev.pool.slot3.agenticpostgresql.com"
DIRECT = "dev.direct.slot3.agenticpostgresql.com"


class _Socket:
    def __init__(self, answer: bytes) -> None:
        self.answer = answer
        self.sent: list[bytes] = []
        self.closed = False

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def recv(self, size: int) -> bytes:
        return self.answer[:size]

    def close(self) -> None:
        self.closed = True


class _Wrapped:
    def __enter__(self) -> _Wrapped:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


class _Context:
    """A client context whose handshake raises `failure`, or succeeds."""

    def __init__(self, failure: BaseException | None = None) -> None:
        self.failure = failure
        self.names: list[str] = []

    def wrap_socket(self, raw: Any, *, server_hostname: str) -> _Wrapped:
        self.names.append(server_hostname)
        if self.failure is not None:
            raise self.failure
        return _Wrapped()


def _verification() -> ssl.SSLCertVerificationError:
    error = ssl.SSLCertVerificationError(1, "certificate verify failed")
    error.verify_message = "unable to get local issuer certificate"
    return error


@pytest.mark.parametrize(
    ("answer", "failure", "expected"),
    [
        (b"S", None, "ready"),
        (b"S", ssl.SSLEOFError(8, "EOF occurred in violation of protocol"), "pending"),
        (b"S", _verification(), "pending"),
        (b"N", None, "unknown"),
        (b"S", ssl.SSLError(1, "wrong version number"), "unknown"),
    ],
    ids=["verified", "eof-no-certificate-yet", "does-not-verify", "no-S", "other-tls-failure"],
)
def test_each_reading_is_one_of_three_outcomes(
    answer: bytes, failure: BaseException | None, expected: str
) -> None:
    raw = _Socket(answer)
    context = _Context(failure)
    state, reason = branch_door.check(
        POOL,
        context=context,
        connect=lambda address, timeout: raw,  # type: ignore[arg-type]
    )
    assert state == expected, (state, reason)
    assert raw.sent == [branch_door.SSL_REQUEST] and raw.closed
    assert (reason == "") == (expected == "ready")
    if answer == b"S":
        assert context.names == [POOL], "the name is the SNI the edge routes by"


def test_no_connection_is_unknown_not_pending() -> None:
    def refused(address: Any, timeout: float) -> Any:
        raise ConnectionRefusedError(111, "Connection refused")

    state, reason = branch_door.check(POOL, context=_Context(), connect=refused)  # type: ignore[arg-type]
    assert state == "unknown" and "did not accept a connection" in reason


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_ready_waits_for_both_names() -> None:
    """`ready` is returned only on the poll where BOTH names verify: the pool
    name from the first poll, the direct name from the third."""
    clock = _Clock()
    polls: dict[str, int] = {POOL: 0, DIRECT: 0}

    def probe(host: str) -> tuple[str, str]:
        polls[host] += 1
        if host == DIRECT and polls[host] < 3:
            return "pending", f"the edge holds no certificate for {host} yet"
        return "ready", ""

    assert branch_door.wait((POOL, DIRECT), probe=probe, clock=clock, sleep=clock.sleep) == (
        "ready",
        None,
    )
    assert polls == {POOL: 3, DIRECT: 3}
    assert clock.slept == [branch_door.DOOR_INTERVAL_SECONDS] * 2


@pytest.mark.parametrize(
    ("direct", "expected"),
    [("pending", "pending"), ("unknown", "unknown")],
    ids=["edge-answered", "could-not-check"],
)
def test_a_door_not_issued_in_time_is_pending_with_a_reason(direct: str, expected: str) -> None:
    """At `DOOR_SECONDS` the door is said, not guessed: `pending` with the name's
    own reason when the edge answered, `unknown` when a check could not run."""
    clock = _Clock()

    def probe(host: str) -> tuple[str, str]:
        return ("ready", "") if host == POOL else (direct, f"{host}: {direct}")

    door, reason = branch_door.wait((POOL, DIRECT), probe=probe, clock=clock, sleep=clock.sleep)
    assert door == expected
    assert reason is not None and f"not open after {branch_door.DOOR_SECONDS} s" in reason
    assert DIRECT in reason and POOL not in reason
    assert clock.now >= branch_door.DOOR_SECONDS
