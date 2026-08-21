"""What the public internet can reach of the agent plane (AGT-PUBLIC-001).

Run from a network that is **not** the deployment host, for the reason
`test_session5_public_api.py` states: a request made *on* the host traverses
loopback and the host's own routing table, so it reaches services the world
cannot and reports "closed" for ports the world can. Neither answer is about the
public boundary.

**A negative from an instrument that can see nothing is not a boundary.** 443 is
asserted open and the agent route asserted answering, from this network, in this
run, before anything is reported refused.

**Why this is a separate requirement from `SEC-API-001`.** That one was written
in Session 5 over the REST and documentation routes, and a claim is measured in
exactly one environment (ADR 0045) -- so widening it to cover a surface that did
not exist would move a Session 5 claim into Session 8 through `max()` and
withdraw it from Session 5's evidence (ADR 0089, D279, ADR 0132). A new id is the
only shape that leaves both sessions' evidence saying what it said. It is the
same argument `STO-PUBLIC-001` was created under, and it is written out again
because the shortcut is tempting every time.

**The health surface is the sharp half.** `custom_route` mounts at the
application root and is **not** behind the verifier (D442): both health paths
answer 200 on the container's own socket. The only thing keeping them off the
internet is that no Traefik router names them (ADR 0128), and this module is the
one place that difference is observable.

**Never executed.** No deployment has started an MCP container anywhere.
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

#: What an MCP endpoint requires. Measured (D458): naming only
#: `application/json` is answered **406**, not 401 -- so an anonymous probe sent
#: the obvious way would be refused by content negotiation and would report a
#: boundary it never reached.
MCP_ACCEPT = "application/json, text/event-stream"

#: The agent plane's own listening port. Not published by design -- it is
#: reached only over the `internal` and `edge` networks -- so it is scanned
#: rather than reasoned about.
MCP_PORT = 8080


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


def post(url: str, *, accept: str = MCP_ACCEPT) -> tuple[int, str]:
    """One anonymous JSON-RPC POST. Returns, never judges."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    request = urllib.request.Request(  # noqa: S310
        url, data=body.encode("utf-8"), method="POST"
    )
    request.add_header("Accept", accept)
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(  # noqa: S310
            request, timeout=REQUEST_TIMEOUT, context=ssl.create_default_context()
        ) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, ""


def get(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, method="GET")  # noqa: S310
    request.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(  # noqa: S310
            request, timeout=REQUEST_TIMEOUT, context=ssl.create_default_context()
        ) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, ""


def test_the_agent_plane_answers_from_off_host_and_refuses_an_anonymous_caller(
    project_a: dict[str, Any], public_ipv4: str
) -> None:
    """**AGT-PUBLIC-001.** Control first, negative after.

    **The control.** 443 is open from this network and the agent route answers
    *something*. A route that refused the connection would be indistinguishable
    from one that is not published, and the refusal below would then be a fact
    about this scanner rather than about the boundary.

    **The negative.** An anonymous JSON-RPC call is answered **401** and the body
    carries no tool name. A tool list is a description of a deployment's data
    surface -- resources, the scopes they need, the ceilings they carry -- and it
    is not public.

    Goes red if: the plane loses its verifier; the route stops answering, in
    which case this says so rather than reporting a boundary it did not measure.
    """
    assert port_is_open(public_ipv4, 443), (
        f"443 is closed at {public_ipv4}, so this scanner cannot reach the host at all "
        "and every refusal below is meaningless"
    )

    route = (project_a.get("routes") or {}).get("mcp") or {}
    url = route.get("url")
    assert route.get("status") == "ready" and url, (
        f"this project publishes no ready agent route (status {route.get('status')!r}), "
        "so there is no public surface here to measure"
    )
    assert urlsplit(str(url)).scheme == "https"

    status, body = post(str(url))
    assert status != 0, (
        "the agent route did not answer from off-host at all. That is not a boundary -- "
        "it is a route that is not published, and nothing below measures one"
    )
    assert status == 401, (
        f"an anonymous JSON-RPC call to the agent plane answered {status}, not 401. "
        f"A 406 would mean this probe was refused by content negotiation before "
        f"authentication ran (D458); body: {body[:200]}"
    )
    for name in ("list_resources", "describe_resource", "query_resource", "run_report"):
        assert name not in body, (
            f"the anonymous refusal names the tool {name!r}. A tool list describes this "
            "deployment's data surface and is not public"
        )


def test_the_health_routes_are_not_reachable_from_the_public_internet(
    project_a: dict[str, Any], public_ipv4: str
) -> None:
    """**AGT-PUBLIC-001, ADR 0128.** Private by the ABSENCE of a route.

    Both paths answer **200 on the container's own socket** -- measured -- and
    `custom_route` mounts them at the application root, outside the verifier
    (D442). So nothing in the runtime refuses them, and the only reason a
    stranger cannot read them is that no Traefik router names them.

    That makes this the proof, and it is why it is asserted from here rather
    than on the host: on the host the same request reaches the container
    directly and returns 200, which would look like a failure of a boundary that
    is working.

    A 404 is the expected answer -- Traefik's own, for a path no rule matches.
    """
    assert port_is_open(public_ipv4, 443), f"443 is closed at {public_ipv4}"

    url = ((project_a.get("routes") or {}).get("mcp") or {}).get("url")
    assert url, "no agent route is published; there is nothing to be private beside"
    origin = str(url).rsplit("/", 1)[0]

    for path in ("/health/live", "/health/ready"):
        status, body = get(f"{origin}{path}")
        assert status in (404, 403), (
            f"{path} answered {status} from the public internet. It answers 200 on the "
            "container's socket and is behind no verifier, so anything other than a "
            "routing refusal means the edge is publishing the readiness of a deployment"
        )
        assert "capability_lock" not in body and "key_set" not in body, (
            "the public answer names what the readiness probe holds"
        )


def test_the_agent_planes_own_port_is_not_published(public_ipv4: str) -> None:
    """**AGT-PUBLIC-001.** Scanned, not inferred from the Compose model.

    The model is a description of intent; a published port is a fact about the
    host's firewall and Docker's own iptables rules, which is a different thing
    and has been wrong before. The agent plane joins `internal` and `edge` and
    needs no host port at all.
    """
    assert port_is_open(public_ipv4, 443), (
        f"443 is closed at {public_ipv4}; this scanner cannot see the host, so a closed "
        "port below would be a fact about this network"
    )
    assert not port_is_open(public_ipv4, MCP_PORT), (
        f"the agent plane's container port {MCP_PORT} is reachable from the public "
        "internet. It is served only through the edge, which terminates TLS and applies "
        "the router; a direct port bypasses both"
    )
