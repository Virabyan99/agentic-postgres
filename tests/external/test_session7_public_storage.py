"""What the public internet can reach of the storage surface (STO-PUBLIC-001).

Run from a network that is not the deployment host, for the reason
``test_session5_public_api.py`` states: a request made *on* the host traverses
loopback and the host's own routing table, so it reaches services the world
cannot and reports "closed" for ports the world can reach. Neither answer is
about the public boundary.

**A negative from an instrument that can see nothing is not a boundary.** 443 is
asserted open and the storage route asserted answering, from this network, in
this run, before anything is reported refused.

**Why this is a separate requirement from SEC-API-001.** That one was written in
Session 5 over the REST and documentation routes, and a claim is measured in
exactly one environment (ADR 0045) -- so widening it to cover a surface that did
not exist would move a Session 5 claim into Session 7 through ``max()`` and
withdraw it from Session 5's evidence (ADR 0089, D279). A new id is the only
shape that leaves both sessions' evidence saying what it said.

**Never executed.** Like every Session 7 proof, this waits for a deployment that
has started a storage container. There has not been one.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from agentic_postgres import naming

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment("APG_PUBLIC_IPV4", "APG_PROJECT_A_OUTPUTS"),
]

CONNECT_TIMEOUT = 5.0
REQUEST_TIMEOUT = 20

#: The storage container's own listening port. Not published by design -- it is
#: reached only over the `internal` and `edge` networks -- so it is scanned
#: rather than reasoned about.
STORAGE_PORT = 8080


@pytest.fixture(scope="module")
def project_a() -> dict[str, Any]:
    return json.loads(Path(os.environ["APG_PROJECT_A_OUTPUTS"]).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def public_ipv4() -> str:
    return os.environ["APG_PUBLIC_IPV4"]


def port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT):
            return True
    except OSError:
        return False


def fetch(url: str, *, method: str = "GET") -> tuple[int, str]:
    request = urllib.request.Request(url, method=method)  # noqa: S310
    request.add_header("Accept", "application/json")
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(  # noqa: S310
            request, timeout=REQUEST_TIMEOUT, context=context
        ) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, ""


def test_the_storage_surface_refuses_an_anonymous_caller_from_off_host(
    project_a: dict[str, Any], public_ipv4: str
) -> None:
    """STO-PUBLIC-001, control first and negatives after.

    **The control.** 443 is open from here and the storage route answers. A
    route that refused the connection would be indistinguishable from one that
    is not published, and every refusal below would then be a fact about this
    scanner's network.

    **Every endpoint refuses without a credential**, and refuses with 401 rather
    than 404. The distinction is the whole content: a 404 to an anonymous caller
    would mean the ownership filter had run before authentication, and an
    anonymous prober could then tell a real object id from an invented one --
    which is precisely what `STO-OWN-001` denies to an *authenticated* stranger.
    Authentication comes first, so the anonymous answer must be the same for
    every id.

    **The container's own port is not published.** Scanned directly rather than
    inferred from the Compose model, which is a description of intent.

    Goes red if: the storage router loses its authentication; the container
    publishes a host port; the route stops answering, in which case every
    negative here is untrustworthy and this says so.
    """
    assert port_is_open(public_ipv4, 443), (
        f"443 is closed at {public_ipv4}, so this scanner cannot reach the host at all "
        "and every refusal below is meaningless"
    )

    route = project_a.get("routes", {}).get("storage") or {}
    url = route.get("url")
    assert route.get("status") == "ready" and url, (
        f"this project publishes no ready storage route (status {route.get('status')!r}), "
        "so there is no public surface here to measure"
    )
    assert urlsplit(url).scheme == "https"

    base = str(url).rstrip("/")
    known = f"{base}/upload-intents"
    status, body = fetch(known, method="POST")
    assert status != 0, (
        "the storage route did not answer from off-host at all. That is not a boundary "
        "-- it is a route that is not published, and nothing below measures one"
    )
    assert status == 401, (
        f"an anonymous POST to the storage surface answered {status}; it must be 401"
    )
    assert "upload_url" not in body and "object_id" not in body

    # Two invented ids. Both must answer identically, and both must be 401
    # rather than 404: an anonymous caller learns nothing about what exists.
    first, second = uuid.uuid4(), uuid.uuid4()
    answers = {
        fetch(f"{base}/objects/{identifier}/download-url")[0] for identifier in (first, second)
    }
    assert answers == {401}, (
        f"anonymous download requests answered {answers}; a 404 here would mean the "
        "ownership filter ran before authentication, and an anonymous prober could "
        "then distinguish a real object id from an invented one"
    )

    deleted, _ = fetch(f"{base}/objects/{first}", method="DELETE")
    assert deleted == 401, f"an anonymous DELETE answered {deleted}"

    assert not port_is_open(public_ipv4, STORAGE_PORT), (
        f"the storage container's own port {STORAGE_PORT} is reachable from off-host. "
        "It is published to no host interface by design and is reached only over the "
        "internal and edge networks"
    )


def test_the_published_storage_path_is_the_derived_one(project_a: dict[str, Any]) -> None:
    """The route this scanner probed is the one `naming` derives.

    Without this, the test above could pass against a route published somewhere
    else entirely -- it reads the URL out of the deployed document, so it
    measures whatever that document happens to name. Tying the published path
    back to the derivation is what makes the probe a probe of *this* surface.

    Offline arithmetic in an external module on purpose: it needs no host, and
    splitting it into a different environment would put two halves of one
    question in two evidence files (ADR 0045).
    """
    app = (project_a.get("routes", {}).get("app") or {}).get("url") or ""
    storage = (project_a.get("routes", {}).get("storage") or {}).get("url") or ""
    assert app and storage, "this project publishes no application or storage route"
    assert storage.rstrip("/") == f"{app.rstrip('/')}{naming.STORAGE_PATH_SUFFIX}", (
        f"the published storage route {storage!r} is not the application route plus "
        f"{naming.STORAGE_PATH_SUFFIX!r}. Traefik orders these two routers by rule "
        "LENGTH rather than specificity (ADR 0108), so a storage path that is not the "
        "application path plus a suffix is a path the application router may swallow"
    )
