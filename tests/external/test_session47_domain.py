"""Session 47's domain move, read from the outside (ADR 0299; D2946, D2964, D2966, D2985).

`OPS-DOMAIN-001` (claim `domain_live`): after the cutover, from the
workstation, by the public names alone --

* the site answers at `site_build.SITE_URL` and its `www.` with THIS tree's
  build (its `apg-site-digest` meta, D2883's identity);
* the console and the management API answer on `site_build.CONTROL_DOMAIN`,
  the name the control project's deployed document routes to;
* the SQL relay's name and each kept slot's two doors present a certificate
  for their own name under the new zone (the doors through PostgreSQL's own
  `SSLRequest`, as a client connects -- the edge decides by SNI);
* the old site's apex and `www.` answer **301** to the same path and query on
  the new apex, and the old `control.` answers **308** to the same path and
  query on the new one -- for a POST too, so the old CLI's request is never
  turned into a GET (rig 47c, D2985) -- and **the old API name no longer
  serves the API**: its answer is that redirect, never the API's own.

Every request goes to a public name; nothing follows a redirect (each is read
as it is answered); no credential is sent. **No SSH, no process door**
(D2174). **None of these proofs has ever executed.**
"""

from __future__ import annotations

import ast
import json
import os
import re
import socket
import ssl
import struct
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from agentic_postgres import naming, site_build

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment("APG_CONTROL_OUTPUTS"),
]

TIMEOUT = 30
#: ADR 0299: the zone the customer-facing names moved from. It keeps the store
#: and the operator's appliance names (D2964), and its apex, `www.` and
#: `control.` redirect for twelve months (D2966; their removal is 2027-10-29).
FORMER_ZONE = "agenticpostgresql.com"
#: The slots whose names moved at the cutover (Sheets R2c, R2d): the kept
#: customer project and the first person's. Each slot's domain is `<slot>.<zone>`.
MOVED_SLOTS = ("slot3", "slot10")
#: The path and query each redirect must carry unchanged.
PROBE_PATH = "/docs/connecting/?from=domain-proof"
#: As every proof's requests (D2728): Pages refuses urllib's default agent.
USER_AGENT = "agentic-postgres-proof"
DIGEST_META = re.compile(r'<meta name="apg-site-digest" content="([0-9a-f]{64})">')
#: PostgreSQL's SSLRequest: length 8, code 80877103 (the protocol's own number).
SSL_REQUEST = struct.pack("!ii", 8, 80877103)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def ask(method: str, url: str) -> tuple[int, dict[str, str], bytes]:
    """One request, its redirect read rather than followed: status, headers, body."""
    opener = urllib.request.build_opener(
        _NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context())
    )
    opener.addheaders = [("User-Agent", USER_AGENT)]
    data = b"{}" if method == "POST" else None
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 -- public names
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read()


def certificate_names(host: str, port: int, postgres: bool) -> list[str]:
    """The names the certificate `host:port` presents carries, verified against
    this machine's authorities FOR `host` (a mismatch raises). For a door, the
    TLS begins after PostgreSQL's `SSLRequest` is answered `S`."""
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=TIMEOUT) as raw:
        if postgres:
            raw.sendall(SSL_REQUEST)
            answer = raw.recv(1)
            assert answer == b"S", f"{host}:{port} answered {answer!r} to SSLRequest"
        with context.wrap_socket(raw, server_hostname=host) as tls:
            names = [value for kind, value in tls.getpeercert().get("subjectAltName", ())
                     if kind == "DNS"]  # fmt: skip
    return names


@pytest.fixture(scope="module")
def zone() -> str:
    """The new zone, from the build's own constants: the site's apex is the
    control domain's zone (D2962)."""
    zone = naming.sql_relay_zone(site_build.CONTROL_DOMAIN)
    assert site_build.SITE_URL == f"https://{zone}", (site_build.SITE_URL, zone)
    assert zone != FORMER_ZONE
    return zone


@pytest.fixture(scope="module")
def control_host() -> str:
    """The control route's host in the control project's DEPLOYED document --
    which must be the build's `CONTROL_DOMAIN`."""
    document = json.loads(Path(os.environ["APG_CONTROL_OUTPUTS"]).read_text(encoding="utf-8"))
    route = (document.get("routes") or {}).get("control") or {}
    assert route.get("status") == "ready" and route.get("url"), route
    host = str(urlsplit(route["url"]).hostname)
    assert host == site_build.CONTROL_DOMAIN, (host, site_build.CONTROL_DOMAIN)
    return host


def test_the_site_answers_under_its_domain(zone: str) -> None:
    """The apex and `www.` serve THIS tree's build, read by its digest."""
    for base in (site_build.SITE_URL, f"https://www.{zone}"):
        status, _, body = ask("GET", base + "/")
        assert status == 200, (base, status)
        found = DIGEST_META.search(body.decode("utf-8", "replace"))
        assert found and found.group(1) == site_build.digest(), (base, found and found.group(1))


def test_the_console_and_the_api_answer_on_the_control_name(control_host: str) -> None:
    """The console's page and the API's own refusal of an unsigned request --
    `authentication_failed`, the API's word -- on the new control name."""
    status, _, body = ask("GET", naming.console_origin(control_host) + "/console/")
    assert status == 200 and b"<title>" in body, status
    status, headers, body = ask("GET", site_build.CONTROL_ENDPOINT + "/me")
    assert status == 401, (status, body[:200])
    assert json.loads(body).get("error") == "authentication_failed", body[:200]
    assert "location" not in {key.lower() for key in headers}


def test_the_relay_and_the_doors_present_their_own_names(control_host: str, zone: str) -> None:
    """The relay's name on 443, and each moved slot's two doors on 5432 through
    PostgreSQL's `SSLRequest`, each presenting a certificate verified for that
    name -- a name the edge has no certificate for fails here."""
    relay = naming.sql_relay_host(control_host)
    assert relay == f"sql.{zone}"
    assert relay in certificate_names(relay, 443, postgres=False) or any(
        name.startswith("*.") and relay.endswith(name[1:])
        for name in certificate_names(relay, 443, postgres=False)
    )
    for slot in MOVED_SLOTS:
        for door in naming.endpoint_hosts(f"{slot}.{zone}"):
            names = certificate_names(door, 5432, postgres=True)
            assert door in names or any(
                name.startswith("*.") and door.endswith(name[1:]) for name in names
            ), (door, names)


@pytest.mark.parametrize(
    ("old", "new", "status"),
    [
        (f"https://{FORMER_ZONE}", "SITE", 301),
        (f"https://www.{FORMER_ZONE}", "SITE", 301),
        (f"https://control.{FORMER_ZONE}", "CONTROL", 308),
    ],
)
def test_the_old_names_redirect_to_the_same_path(old: str, new: str, status: int) -> None:
    """D2946 (6), D2966: the old site 301s and the old console name 308s
    (D2985), each to the same path and query under the new names."""
    target = (
        site_build.SITE_URL if new == "SITE" else naming.console_origin(site_build.CONTROL_DOMAIN)
    )
    answered, headers, _ = ask("GET", old + PROBE_PATH)
    location = {key.lower(): value for key, value in headers.items()}.get("location")
    assert (answered, location) == (status, target + PROBE_PATH), (old, answered, location)


def test_the_old_api_name_no_longer_serves_the_api() -> None:
    """The old `control.` answers an API request -- a GET and the old CLI's
    POST alike -- with the 308 to the same path on the new name, never with the
    API's own answer: a 308 keeps the POST a POST, and nothing here follows it."""
    old = f"https://control.{FORMER_ZONE}/api" + naming.CONTROL_PATH_SUFFIX
    for method, path in (("GET", "/me"), ("POST", "/sessions")):
        answered, headers, body = ask(method, old + path)
        location = {key.lower(): value for key, value in headers.items()}.get("location")
        assert answered == 308, (method, path, answered, body[:200])
        assert location == site_build.CONTROL_ENDPOINT + path, (method, location)
        assert b"authentication_failed" not in body and b"malformed_request" not in body


def test_this_module_uses_no_ssh() -> None:
    """D2174's rule for a customer proof: nothing here reaches the host but by
    its public names. Read from this file's own text and syntax."""
    text = Path(__file__).read_text(encoding="utf-8")
    for needle in ("para" + "miko", '"s' + 'sh"', "ss" + "h_destination", "ss" + "h-agent"):
        assert needle not in text, needle
    tree = ast.parse(text)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "subprocess" not in imported, imported
