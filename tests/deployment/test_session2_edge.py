"""The edge plane as it actually runs: TLS, log redaction, health routing.

Host-local half of SEC-TLS-001. The public half — that an unrelated network sees
the same thing — lives in ``tests/external/test_session2_public_edge.py``,
because a test run on the host can be satisfied by a loopback path that no
outside client can reach.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres.host_config import EDGE_STACK_NAME
from agentic_postgres.naming import HEALTH_ROUTE_PATH

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]


def fetch(
    url: str, *, host_header: str | None = None, verify: bool = True
) -> tuple[int, dict[str, str], bytes]:
    """Fetch a URL without following redirects, returning status, headers, body.

    Redirects are not followed because the redirect itself is the assertion in
    half these tests, and urllib would otherwise turn a 301 into a 200.
    """

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: Any, **kwargs: Any) -> None:
            return None

    context = ssl.create_default_context()
    if not verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=context))
    # S310: the scheme is written literally at every call site below, always
    # http or https, and the host comes from the deployed document rather than
    # from anything a caller supplies. There is no path by which a file: or
    # custom scheme reaches here.
    request = urllib.request.Request(url)  # noqa: S310
    if host_header:
        request.add_header("Host", host_header)

    try:
        with opener.open(request, timeout=20) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


@pytest.fixture(scope="module")
def hostname(project_a: dict[str, Any]) -> str:
    return project_a["project"]["domain"]


# ---------------------------------------------------------------------------
# OPS-HEALTH-001 — the reserved route answers, and only through the edge
# ---------------------------------------------------------------------------


def test_the_health_route_answers_over_https(hostname: str) -> None:
    status, _, body = fetch(f"https://{hostname}{HEALTH_ROUTE_PATH}")
    assert status == 200, status
    payload = json.loads(body)
    assert payload["status"] == "ok"
    assert payload["session"] == 2


def test_the_health_route_identifies_its_own_project(
    hostname: str, project_a: dict[str, Any]
) -> None:
    """A shared edge that answers with the wrong project key is a routing bug
    that a bare 200 cannot distinguish from success."""
    _, _, body = fetch(f"https://{hostname}{HEALTH_ROUTE_PATH}")
    assert json.loads(body)["project_key"] == project_a["project"]["key"]


def test_the_deployed_document_agrees_with_the_live_route(
    project_a: dict[str, Any], hostname: str
) -> None:
    recorded = project_a["routes"]["health"]
    # `ready`, not `available`. The enum for this field in
    # schemas/outputs.schema.json is ["ready", "unavailable"], and the deploy
    # writes what the schema accepts. This asserted a word the document is not
    # permitted to contain, so it could only ever fail -- and it first ran
    # against a route that was answering 200 from two networks.
    assert recorded["status"] == "ready", recorded
    assert recorded["url"] == f"https://{hostname}{HEALTH_ROUTE_PATH}", recorded


def test_an_unrouted_path_is_not_served(hostname: str) -> None:
    status, _, _ = fetch(f"https://{hostname}/{secrets.token_hex(8)}")
    assert status == 404, f"an unrouted path returned {status}"


# ---------------------------------------------------------------------------
# SEC-TLS-001 — transport policy, measured on the host
# ---------------------------------------------------------------------------


def test_http_redirects_permanently_to_https(hostname: str) -> None:
    status, headers, _ = fetch(f"http://{hostname}{HEALTH_ROUTE_PATH}")
    assert status == 301, status
    assert headers["Location"].startswith(f"https://{hostname}"), headers.get("Location")


def test_hsts_is_present_on_the_https_response(hostname: str, project_a: dict[str, Any]) -> None:
    """HSTS is withheld until the certificate is trusted.

    Sending it while a staging certificate is in play would pin browsers to an
    origin they cannot validate, and the recovery is a cache expiry rather than
    a deploy. The assertion therefore follows the recorded ACME environment
    instead of demanding the header unconditionally.
    """
    _, headers, _ = fetch(f"https://{hostname}{HEALTH_ROUTE_PATH}")
    header = headers.get("Strict-Transport-Security")

    if project_a["tls"]["acme_environment"] != "production":
        assert header is None, f"HSTS is set while on staging certificates: {header!r}"
        pytest.skip("staging ACME environment: HSTS is deliberately withheld")

    assert header is not None, "no HSTS header on a production certificate"
    max_age = re.search(r"max-age=(\d+)", header)
    assert max_age and int(max_age.group(1)) >= 15_552_000, header


def test_tls_one_dot_one_is_refused(hostname: str) -> None:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.maximum_version = ssl.TLSVersion.TLSv1_1

    import socket

    with pytest.raises((ssl.SSLError, OSError)):
        with socket.create_connection((hostname, 443), timeout=15) as raw:
            with context.wrap_socket(raw, server_hostname=hostname):
                pass


def test_the_recorded_certificate_is_the_one_being_served(
    hostname: str, project_a: dict[str, Any]
) -> None:
    """Binds the deployed document to the live socket.

    Without this the document's fingerprint could describe a certificate that
    was replaced hours ago and nothing would notice.
    """
    import hashlib
    import socket

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((hostname, 443), timeout=15) as raw:
        with context.wrap_socket(raw, server_hostname=hostname) as tls:
            served = hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()

    assert project_a["tls"]["certificate_sha256"] == served, (
        "the deployed document records a certificate that is not being served"
    )


def test_the_acme_state_file_matches_the_recorded_environment(
    as_root, project_a: dict[str, Any]
) -> None:
    """Production state is never reached by re-running an earlier command."""
    del as_root
    environment = project_a["tls"]["acme_environment"]
    assert environment in {"staging", "production"}, environment

    state = Path(f"/var/lib/agentic-postgres/edge/acme/{environment}.json")
    assert state.is_file(), f"{state} does not exist"
    mode = oct(state.stat().st_mode & 0o777)
    assert mode == "0o600", mode


# ---------------------------------------------------------------------------
# SEC-LOG-001 — the access log keeps no request content
# ---------------------------------------------------------------------------


def test_no_query_string_reaches_the_access_log(hostname: str, as_root, sh) -> None:
    """The real proof behind the offline Traefik version floor.

    ``bin/lock-versions.sh --check`` can only assert the locked Traefik is new
    enough to *have* ``queryParameters.defaultMode``. Whether redaction is on is
    a property of the running process, and this is the only thing that measures
    it: send a value nothing else could produce, then look for it.
    """
    del as_root
    sentinel = f"apgsentinel{secrets.token_hex(12)}"
    status, _, _ = fetch(f"https://{hostname}{HEALTH_ROUTE_PATH}?apg_sentinel={sentinel}")
    assert status == 200, status

    logs = sh("docker", "logs", "--since", "5m", f"{EDGE_STACK_NAME}-traefik-1")
    assert sentinel not in logs, "the access log retained a request query-string value"


def test_no_request_header_value_reaches_the_access_log(hostname: str, as_root, sh) -> None:
    del as_root
    sentinel = f"apgsentinel{secrets.token_hex(12)}"

    request = urllib.request.Request(f"https://{hostname}{HEALTH_ROUTE_PATH}")
    request.add_header("X-Apg-Probe", sentinel)
    request.add_header("Authorization", f"Bearer {sentinel}")
    # S310: literal https scheme, hostname from the deployed document.
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
        assert response.status == 200

    logs = sh("docker", "logs", "--since", "5m", f"{EDGE_STACK_NAME}-traefik-1")
    assert sentinel not in logs, "the access log retained a request header value"


def test_the_log_sentinel_would_actually_be_visible(as_root, sh, hostname: str) -> None:
    """Guard the guard: prove the log is being read at all.

    Without this, a typo in the container name would produce empty output and
    two green tests that measured nothing.

    It cannot look for the health *path*: ADR 0019 drops `RequestPath` precisely
    because that field carries the query string, and dropping it is the only way
    Traefik can keep a token out of a log. This asserted the presence of the one
    field the edge is configured to remove, so it failed against a correctly
    configured edge -- the guard contradicted the decision it was guarding.

    `RequestHost` and `RouterName` survive that drop, per the same decision, so
    they are what proves an access-log line for the route under test was
    recorded.
    """
    del as_root
    logs = sh("docker", "logs", "--since", "10m", f"{EDGE_STACK_NAME}-traefik-1")
    assert logs.strip(), "no Traefik log output was captured; the redaction tests proved nothing"
    assert '"RouterName"' in logs, (
        "no access-log entry was captured, only startup output, so the redaction "
        "tests proved nothing"
    )
    assert hostname in logs, (
        f"the access log records no request for {hostname}, so it is not logging "
        "the requests under test"
    )


def test_the_health_route_is_reachable_only_through_the_edge(
    running_containers: list[dict[str, Any]], as_root, sh
) -> None:
    """The probe answers on the edge network and publishes no port of its own."""
    del as_root
    key = os.environ.get("APG_PROJECT_A_KEY")
    probes = [
        container
        for container in running_containers
        if "edge-probe" in container["Names"] and (key is None or key in container["Names"])
    ]
    assert probes, "no edge probe container is running"

    for container in probes:
        ports = json.loads(
            sh("docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container["ID"])
        )
        published = {port: bindings for port, bindings in (ports or {}).items() if bindings}
        assert not published, f"{container['Names']} publishes {published}"
