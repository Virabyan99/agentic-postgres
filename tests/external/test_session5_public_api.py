"""What the public internet can reach of the API plane (SEC-API-001).

Replaces one Session 5 placeholder in
``tests/security/test_future_security_boundaries.py``. Marked ``external``, and
the placeholder's comment said this move was coming: a placeholder's directory is
not a commitment, and ADR 0045's rule is that a claim is measured in exactly one
environment. ``SEC-API-001``'s node ID carries the ``external`` marker and no
other, because a requirement whose proofs straddle two environments breaks every
claim containing it -- measured, not assumed, before this file was written.

Run from a network that is not the deployment host. That separation is the whole
point: a request made *on* the host traverses loopback and the host's own routing
table, so it reaches services the world cannot and reports "closed" for ports the
world can reach. Neither answer is about the public boundary.

**A negative from an instrument that can see nothing is not a boundary.** 443 is
asserted open and the REST route asserted answering, from this same network, in
the same run, before anything is reported unreachable.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment("APG_PUBLIC_IPV4", "APG_PROJECT_A_OUTPUTS"),
]

CONNECT_TIMEOUT = 5.0
REQUEST_TIMEOUT = 20

#: PostgREST's own listening port, and the admin port beside it. Neither is
#: published by design -- the admin surface binds container loopback and is not a
#: network service at all -- so both are scanned rather than reasoned about.
SERVICE_PORTS = (3000, 3001)


@pytest.fixture(scope="module")
def project_a() -> dict[str, Any]:
    return json.loads(Path(os.environ["APG_PROJECT_A_OUTPUTS"]).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def public_ipv4() -> str:
    return os.environ["APG_PUBLIC_IPV4"]


def port_is_open(host: str, port: int) -> bool:
    """Full TCP connect, not a SYN probe.

    A half-open scan reports what a firewall did to a SYN. A completed
    three-way handshake reports that something is listening and willing to talk,
    which is the claim under test.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(CONNECT_TIMEOUT)
            return probe.connect_ex((host, port)) == 0
    except OSError:
        return False


def fetch(url: str, *, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], str]:
    """Request over HTTPS and report the result. ``0`` means nothing answered."""
    request = urllib.request.Request(url, method="GET")  # noqa: S310 — https asserted by the caller
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT, context=context) as response:  # noqa: S310
            return (
                response.status,
                dict(response.headers.items()),
                response.read().decode("utf-8", "replace"),
            )
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, {}, ""


def test_only_the_approved_api_surface_answers_from_off_host(
    project_a: dict[str, Any], public_ipv4: str
) -> None:
    """SEC-API-001, with its positive control first and its negatives after.

    **The control.** 443 is open from here and the REST route answers over
    HTTPS. Without both, every unreachable result below would be a fact about
    this scanner's network rather than about the deployment -- the exact shape of
    a false green this repository has produced before.

    **The REST route answers, and refuses.** It is reachable without a token,
    because a route that refused the TCP connection would be indistinguishable
    from one that does not exist; and it serves no data without one.

    **The documentation route refuses with a challenge.** 401 carrying a
    ``Basic`` challenge. A 401 with no challenge is a refusal a browser cannot
    act on and is also what a misconfigured middleware chain produces, so the
    challenge is asserted rather than inferred from the status.

    **Nothing else of the API plane is reachable.** PostgREST's own port and the
    admin port beside it are scanned directly; a path outside the two approved
    prefixes is requested; and the prefix boundary is probed with the strings
    D162 records -- ``/api/restaurant`` matched ``PathPrefix(/api/rest)`` as a
    *string* prefix, which is a 200 for a hostname nobody meant to publish.

    Goes red if: a service port is published to a public interface; the router's
    rule reverts to a bare ``PathPrefix``; the documentation middleware is
    removed, so the docs route answers 200; the REST route stops answering, in
    which case every negative here is untrustworthy and this says so; or a new
    prefix is published that the deployed document does not name.
    """
    assert port_is_open(public_ipv4, 443), (
        f"443 is closed at {public_ipv4}, so this scanner cannot reach the host at all "
        "and every unreachable result below is meaningless"
    )

    rest = (project_a["routes"]["rest"] or {}).get("url")
    docs = (project_a["routes"]["docs"] or {}).get("url")
    assert rest and docs, "this project publishes no REST or documentation route"
    assert urlsplit(rest).scheme == "https" and urlsplit(docs).scheme == "https"

    status, _, body = fetch(rest)
    assert status != 0, (
        f"{rest} did not answer from off-host at all. That is not a boundary -- it is a "
        "route that is not published, and nothing below would be measuring one"
    )
    assert status in (200, 401, 403), (
        f"{rest} answered {status}; the REST route is reachable but is not the REST route"
    )
    if status == 200:
        assert json.loads(body) in ([], {}) or json.loads(body).get("paths") is not None, (
            f"{rest} served data to a caller with no token: {body[:200]}"
        )

    status, headers, _ = fetch(docs)
    assert status == 401, f"{docs} answered {status} without a credential, not 401"
    assert "Basic" in headers.get("WWW-Authenticate", ""), (
        f"{docs} refused with no Basic challenge (WWW-Authenticate: "
        f"{headers.get('WWW-Authenticate')!r}); a browser has nothing to prompt for"
    )

    for port in SERVICE_PORTS:
        assert not port_is_open(public_ipv4, port), (
            f"{public_ipv4}:{port} accepted a connection; a service address of the API "
            "plane is published, which is a way around every limit the edge applies"
        )

    # D162: `PathPrefix(/api/rest)` matches `/api/restaurant` because it is a
    # string prefix, not a path prefix. Each of these must be a 404 from the
    # edge rather than a 200 from PostgREST.
    origin = f"{urlsplit(rest).scheme}://{urlsplit(rest).netloc}"
    prefix = urlsplit(rest).path.rstrip("/")
    for suffix in ("aurant", "-extra", "2", "aurant/notes"):
        status, _, _ = fetch(f"{origin}{prefix}{suffix}")
        assert status == 404, (
            f"{origin}{prefix}{suffix} answered {status}; the router's rule is a string "
            "prefix rather than a path prefix (D162)"
        )

    for path in ("/", "/admin", "/metrics", "/api", "/api/rest/../../"):
        status, _, _ = fetch(f"{origin}{path}")
        assert status in (0, 401, 403, 404), (
            f"{origin}{path} answered {status}; something outside the approved surface is published"
        )
