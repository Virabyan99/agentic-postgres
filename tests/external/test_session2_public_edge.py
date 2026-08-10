"""What the public internet can reach, measured from somewhere else.

This module runs from a network that is not the deployment host — in practice
the development machine. That separation is the whole point. A port scan run on
the host traverses loopback and the host's own routing table, so it can report
"closed" for a port the rest of the world can reach, and "open" for one only the
host can. Neither answer is about the public boundary.

``SEC-NET-001`` is proved here in its strongest form: the direct PostgreSQL
endpoint is unreachable because nothing is listening, no route carries it, and
every endpoint the deployed document reports is a **loopback** address rather
than one the world could dial.

That last clause used to read "the documents still describe it as unavailable".
It was true for two sessions and Session 4 made it false, by design: a project
now publishes `pooled` and `direct` endpoints in its deployed document, and they
are the near end of a developer's SSH tunnel (ADR 0044). The absence was standing
in for the property, and the property is that the address is not reachable
(D125, ADR 0047).
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres.naming import HEALTH_ROUTE_PATH

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment("APG_PUBLIC_IPV4", "APG_PROJECT_A_OUTPUTS"),
]

#: Ports a project could plausibly leak. 5432 is the requirement; the rest are
#: the neighbours that would indicate the same class of mistake.
FORBIDDEN_PORTS = (5432, 6432, 8080, 8443, 9000, 2375, 2376, 5433)

CONNECT_TIMEOUT = 5.0


def port_is_open(host: str, port: int, family: int = socket.AF_INET) -> bool:
    """Full TCP connect, not a SYN probe.

    A half-open scan reports what a firewall did to a SYN. A completed
    three-way handshake reports that something is listening and willing to
    talk, which is the claim under test.
    """
    try:
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.settimeout(CONNECT_TIMEOUT)
            return probe.connect_ex((host, port)) == 0
    except OSError:
        return False


@pytest.fixture(scope="module")
def project_a() -> dict[str, Any]:
    return json.loads(Path(os.environ["APG_PROJECT_A_OUTPUTS"]).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def public_ipv4() -> str:
    return os.environ["APG_PUBLIC_IPV4"]


# ---------------------------------------------------------------------------
# SEC-NET-001 — no public route reaches the direct PostgreSQL endpoint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("port", FORBIDDEN_PORTS)
def test_no_service_port_is_publicly_reachable_over_ipv4(public_ipv4: str, port: int) -> None:
    assert not port_is_open(public_ipv4, port), (
        f"{public_ipv4}:{port} accepted a connection from outside the host"
    )


@pytest.mark.parametrize("port", FORBIDDEN_PORTS)
@pytest.mark.requires_environment("APG_PUBLIC_IPV6")
def test_no_service_port_is_publicly_reachable_over_ipv6(port: int) -> None:
    """IPv6 is scanned separately and only when configured.

    A host with a working AAAA record and an IPv4-only firewall is the classic
    way a port stays open after everyone agrees it is closed.
    """
    address = os.environ["APG_PUBLIC_IPV6"]
    assert not port_is_open(address, port, family=socket.AF_INET6), (
        f"[{address}]:{port} accepted a connection from outside the host"
    )


def test_the_scan_can_detect_an_open_port(public_ipv4: str) -> None:
    """Guard the guard: a scanner that always reports closed proves nothing.

    443 must be open — the same probe, the same host, the opposite answer.
    """
    assert port_is_open(public_ipv4, 443), (
        "443 is closed, so the negative results above are not evidence of anything"
    )


@pytest.mark.parametrize("transport", ["direct", "pooled"])
def test_every_reported_endpoint_is_loopback_or_absent(
    project_a: dict[str, Any], transport: str
) -> None:
    """The document may name an endpoint; it may not name a reachable one.

    This asserted ``status == "unavailable"`` and ``url is None`` for two
    sessions, which was true because no endpoint existed yet. Session 4 makes it
    false on purpose: a project publishes both transports in its deployed
    document, and they are the near end of a developer's SSH tunnel. The
    assertion had encoded the absence rather than the property the absence was
    standing in for (D125, ADR 0047).

    Both states are still checked, so this holds against a Session 2, 3 or 4
    deployment without being told which:

    *Absent* is still absent — a status of ``unavailable`` with a URL beside it
    would be a document contradicting itself.

    *Present* must be loopback, in the host field **and** in the URL, because
    those are two places one address is written and the pair has drifted in this
    repository before. A public or wildcard address here is a database on the
    internet described as a developer convenience.

    And no URL carries a credential. The schema's pattern already refuses one;
    this is the same claim asserted against the bytes that were actually written,
    which is the difference between a schema and a measurement.
    """
    endpoint = project_a["database"][transport]
    status = endpoint["status"]
    assert status in ("available", "unavailable"), endpoint

    if status == "unavailable":
        assert endpoint["url"] is None, endpoint
        assert endpoint.get("host") is None, endpoint
        return

    host = endpoint["host"]
    assert ipaddress.ip_address(host).is_loopback, (
        f"the {transport} endpoint is published at {host}, which is not loopback"
    )

    parsed = urllib.parse.urlsplit(endpoint["url"])
    assert parsed.hostname and ipaddress.ip_address(parsed.hostname).is_loopback, (
        f"the {transport} URL points at {parsed.hostname}, which is not loopback"
    )
    assert parsed.password is None, f"the {transport} URL carries a credential"
    assert parsed.port == endpoint["port"], (
        f"the {transport} URL says port {parsed.port} and the endpoint says "
        f"{endpoint['port']}; two records of one number have drifted"
    )


# ---------------------------------------------------------------------------
# SEC-TLS-001 — the public half
# ---------------------------------------------------------------------------


def test_the_certificate_is_trusted_by_a_default_trust_store(project_a: dict[str, Any]) -> None:
    """Verification is left on. That is the assertion.

    A test that disabled verification here would pass against the staging
    certificate and would never notice that promotion to production had not
    happened.
    """
    hostname = project_a["project"]["domain"]
    context = ssl.create_default_context()
    with socket.create_connection((hostname, 443), timeout=15) as raw:
        with context.wrap_socket(raw, server_hostname=hostname) as tls:
            assert tls.getpeercert(), "no peer certificate was presented"


def test_the_public_health_route_answers(project_a: dict[str, Any]) -> None:
    hostname = project_a["project"]["domain"]
    with urllib.request.urlopen(
        f"https://{hostname}{HEALTH_ROUTE_PATH}", timeout=20, context=ssl.create_default_context()
    ) as response:
        assert response.status == 200
        assert json.loads(response.read())["project_key"] == project_a["project"]["key"]


def test_plain_http_is_redirected_from_outside(project_a: dict[str, Any]) -> None:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: Any, **kwargs: Any) -> None:
            return None

    hostname = project_a["project"]["domain"]
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(f"http://{hostname}{HEALTH_ROUTE_PATH}", timeout=20) as response:
            status, location = response.status, response.headers.get("Location")
    except urllib.error.HTTPError as exc:
        status, location = exc.code, exc.headers.get("Location")

    assert status == 301, status
    assert location and location.startswith("https://"), location
