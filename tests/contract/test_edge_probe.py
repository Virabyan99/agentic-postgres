"""The probe's route matching, which nothing exercised until it broke a proof.

`services/edge-probe/probe.py` compared `self.path` whole against
`/__apg/healthz`. `BaseHTTPRequestHandler.path` carries the query string, so
`/__apg/healthz?x=1` was a 404: Traefik matched `Path(/__apg/healthz)` and routed
the request, and the origin then disagreed with its own router.

That also blocked the only proof that a query string never reaches the access
log (ADR 0019), because that proof has to send one to a route that answers. The
defect survived because no test ran this file at all -- it was reachable only
through a live deployment, and only after TLS verification started working.

The server is driven end to end here, over a real socket on loopback, rather
than by calling the handler with a stubbed request. A reproduction that swaps
out the thing under test is how this repository has been fooled before.
"""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

PROBE_SOURCE = REPO_ROOT / "services" / "edge-probe" / "probe.py"
PROJECT_KEY = "fixture-alpha-dev"


@pytest.fixture(scope="module")
def probe(monkeypatch_module: None = None):
    """Import probe.py by path, with the project key it refuses to default."""
    import os

    os.environ["PROJECT_KEY"] = PROJECT_KEY
    spec = importlib.util.spec_from_file_location("apg_edge_probe", PROBE_SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def base_url(probe) -> Iterator[str]:
    """A real server on an ephemeral loopback port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), probe.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        return exc.code, json.loads(exc.read())


def test_the_health_path_answers(base_url: str) -> None:
    status, body = get(f"{base_url}/__apg/healthz")
    assert status == 200
    assert body["status"] == "ok"
    assert body["project_key"] == PROJECT_KEY


@pytest.mark.parametrize(
    "query",
    ["?x=1", "?apg_sentinel=deadbeef", "?a=1&b=2", "?"],
)
def test_a_query_string_does_not_turn_the_health_path_into_a_404(base_url: str, query: str) -> None:
    """The defect. Traefik routes on the path; the origin must agree with it."""
    status, body = get(f"{base_url}/__apg/healthz{query}")
    assert status == 200, f"query string {query!r} produced {status}"
    assert body["project_key"] == PROJECT_KEY


@pytest.mark.parametrize(
    "path",
    ["/__apg/healthz/", "/__apg/health", "/__apg", "/", "/healthz", "/__apg/healthzz"],
)
def test_exactness_survives_the_fix(base_url: str, path: str) -> None:
    """Stripping the query must not turn the match into a prefix match."""
    status, body = get(f"{base_url}{path}")
    assert status == 404, f"{path!r} should not match the health route"
    assert body == {"status": "not_found"}


def test_an_unmatched_path_is_never_echoed(base_url: str) -> None:
    """An unknown route must reveal nothing a caller supplied.

    The response body and the structured log both carry a fixed constant, so a
    caller cannot write attacker-controlled text into either.
    """
    marker = "apgreflectme12345"
    status, body = get(f"{base_url}/{marker}")
    assert status == 404
    assert marker not in json.dumps(body)
