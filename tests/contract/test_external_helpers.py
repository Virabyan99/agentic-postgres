"""The external suite's pure helpers, proved without a network (D214).

`tests/external/` is collected everywhere and executed only under `-m external`,
which is why D10b requires those modules to be importable with no network at
import time. That makes their pure helpers testable here, and this one needed it:
a case-sensitive header lookup read `None` from a header that was present, and
the only thing that would ever have noticed was an off-host run of the gate.
"""

from __future__ import annotations

import importlib.util

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]


def _load_external_module():
    """Import the external module by path.

    A bare `from test_session5_public_api import ...` works only from inside
    `tests/external/`, because that is the directory pytest puts on `sys.path`
    for the module it is collecting. Loading by path is what lets a proof in one
    directory measure a helper in another -- and it exercises D10b's rule from
    the outside: an external module must be importable with no network at import
    time, and this import is now a place that would fail if it stopped being.
    """
    path = REPO_ROOT / "tests" / "external" / "test_session5_public_api.py"
    spec = importlib.util.spec_from_file_location("apg_external_public_api", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


Headers = _load_external_module().Headers


def test_a_header_is_found_under_any_capitalisation() -> None:
    """RFC 9110 §5.1. Go canonicalises to `Www-Authenticate`; the RFC writes `WWW-`.

    Both spellings are on the wire in this system -- Traefik sends the first and
    the proof asked for the second -- so neither may be privileged.
    """
    headers = Headers([("Www-Authenticate", 'Basic realm="alpha-dev documentation"')])

    for spelling in ("WWW-Authenticate", "Www-Authenticate", "www-authenticate"):
        assert "Basic" in headers.get(spelling, ""), spelling
        assert spelling in headers
        assert headers[spelling].startswith("Basic")


def test_an_absent_header_is_still_absent() -> None:
    """The fix must not make every lookup succeed, which is the way this goes wrong."""
    headers = Headers([("Content-Type", "text/plain")])

    assert headers.get("WWW-Authenticate") is None
    assert headers.get("WWW-Authenticate", "") == ""
    assert "WWW-Authenticate" not in headers
    with pytest.raises(KeyError):
        headers["WWW-Authenticate"]


def test_the_wire_spelling_survives_for_the_failure_message() -> None:
    """Still a dict, because the repr is what made D214 diagnosable in one read."""
    headers = Headers([("Www-Authenticate", "Basic realm=x")])

    assert dict(headers) == {"Www-Authenticate": "Basic realm=x"}
    assert "Www-Authenticate" in repr(headers)
