"""Session 45's look, read from the outside in a real Chromium (ADR 0288).

`UI-LIVE-001` (claim `ui_look_live`) reads the look walk's record
(`APG_LOOK_RECORD_FILE`, written by `tests/external/browser/site_look.py` against
the public site and the deployed console): every page of THIS tree's site --
the routes `site_build.pages()` builds -- and the console's sign-in, at 390 and
1280 px, did not scroll sideways, asked nothing of another origin (every
ATTEMPTED request, blocked ones included), loaded no typeface in `error` and set
JetBrains Mono where it has code (D2849), and drew the 2 px focus ring on the
first Tab. The site's digest in the record is this tree's, and the record is
about the commit the control project is deployed at. **No SSH, no process
door** (D2174). **None of these proofs has ever executed.**
"""

# ruff: noqa: F811 -- the imported names are pytest fixtures.

from __future__ import annotations

import ast
import json
import os
import stat
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from tests.external.test_session38_public_lifecycle import (  # noqa: F401 -- fixtures
    control,
    endpoint,
)

from agentic_postgres import naming, site_build

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment("APG_LOOK_RECORD_FILE", "APG_CONTROL_OUTPUTS"),
]

VIEWPORTS = ([390, 844], [1280, 800])
RING = {"style": "solid", "width": "2px", "color": "rgb(31, 79, 163)", "focus_visible": True}


@pytest.fixture(scope="module")
def look(control: dict[str, Any], endpoint: str) -> dict[str, Any]:
    """The walk's record: private, live, Session 45's, at the public site and
    the control project's console origin, about the deployed commit."""
    path = Path(os.environ.get("APG_LOOK_RECORD_FILE", ""))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600, f"{path} is not 0600"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert (document.get("session"), document.get("kind"), document.get("mode")) == (
        45,
        "look",
        "live",
    )
    assert document.get("dry") is False
    assert document.get("site") == site_build.SITE_URL, document.get("site")
    assert document.get("console") == naming.console_origin(str(urlsplit(endpoint).hostname))
    assert document.get("source_commit") == control["source_commit"], (
        f"the walk names {document.get('source_commit')}, the control project is at "
        f"{control['source_commit']}: a record from another release"
    )
    return document


def _pages(look: dict[str, Any]) -> list[dict[str, Any]]:
    return look["pages"]


def test_the_look_walk_reached_every_page(look: dict[str, Any]) -> None:
    """Every route this tree builds and the console's sign-in, at both widths,
    read without error, the site's pages carrying this tree's digest."""
    routes = sorted(page.route for page in site_build.pages())
    assert sorted(look["routes"]) == routes
    assert look["exit"] == 0
    read = {
        (p["surface"], p["route"], tuple(p["viewport"])) for p in _pages(look) if "error" not in p
    }
    for viewport in VIEWPORTS:
        for route in routes:
            assert ("site", route, tuple(viewport)) in read, (route, viewport)
        assert ("console", "/console/", tuple(viewport)) in read, viewport
    digests = {p["digest"] for p in _pages(look) if p["surface"] == "site"}
    assert digests == {site_build.digest()}, digests


def test_no_page_scrolls_sideways(look: dict[str, Any]) -> None:
    for page in _pages(look):
        width, inner = page["scroll"]
        assert width <= inner, (page["route"], page["viewport"], width, inner)


def test_every_request_stayed_on_its_origin(look: dict[str, Any]) -> None:
    """Every request a page attempted -- the policy's refusals included -- went to
    that page's own origin, and the policy reported no violation."""
    for page in _pages(look):
        origin = look["site"] if page["surface"] == "site" else look["console"]
        assert page["requests"], (page["route"], "the walk read no request at all")
        foreign = [url for url in page["requests"] if not url.startswith(origin + "/")]
        assert not foreign, (page["route"], page["viewport"], foreign)
        assert page["violations"] == [], (page["route"], page["violations"])


def test_both_typefaces_loaded(look: dict[str, Any]) -> None:
    """No family in `error` anywhere; Schibsted Grotesk `loaded` on every page;
    JetBrains Mono `loaded` on a page that sets code -- a face a page does not use
    is `unloaded`, which is not a failure (D2849)."""
    for page in _pages(look):
        assert "error" not in page["fonts"].values(), (page["route"], page["fonts"])
        assert page["fonts"]["Schibsted Grotesk"] == "loaded", (page["route"], page["fonts"])
    mono = {p["route"] for p in _pages(look) if p["fonts"]["JetBrains Mono"] == "loaded"}
    assert "/docs/connecting/" in mono, sorted(mono)


def test_focus_is_visible(look: dict[str, Any]) -> None:
    """The first Tab on every page lands on an element drawing the brief's ring."""
    for page in _pages(look):
        focus = page["focus"]
        assert {key: focus[key] for key in RING} == RING, (page["route"], page["viewport"], focus)


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
