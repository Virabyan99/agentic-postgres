"""Session 47's console look, read from the outside in a real Chromium (ADR 0295 decision 9).

`UI-A11Y-002` (claim `console_look_live`, D3082) reads the console look walk's
record (`APG_CONSOLE_LOOK_RECORD_FILE`, written by
`tests/external/browser/console_look.py` against the deployed console, signed
in through its own form as the probe owner): every signed-in view
`services/console/public/pages.json` names, at 390 and 1280 px, did not scroll
sideways, asked nothing of an origin but the console's own and the SQL
relay's (every ATTEMPTED request, blocked ones included), reported no policy
violation, named every control in its accessibility snapshot, and drew the
2 px focus ring on each of four `Tab`s; and reduced motion stopped the
spinner, the skeleton and the tracker's bar while the default kept them
moving. The record is about the commit the control project is deployed at
and the console origin its document names. **No SSH, no process door**
(D2174). **None of these proofs has ever executed.**

The readings are this module's own functions (`look_problems`,
`motion_problems`), which `tests/contract/test_session47_look_reading.py`
calls offline on records built in the test (D1114: the proof's code, not a
copy of it).
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

from agentic_postgres import naming

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGES = REPO_ROOT / "services" / "console" / "public" / "pages.json"

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment("APG_CONSOLE_LOOK_RECORD_FILE", "APG_CONTROL_OUTPUTS"),
]

VIEWPORTS = ((390, 844), (1280, 800))
#: The brief's ring (ADR 0288 §5, kept by ADR 0295): what each `Tab` must land on.
RING = {"style": "solid", "width": "2px", "color": "rgb(31, 79, 163)", "focus_visible": True}
#: The four `Tab`s `console_look.py` presses on every page.
TABS = 4
#: The views a signed-in person reaches: every view `pages.json` names but these.
SIGNED_OUT = ("accept", "sign-in")
#: The three moving things the brief's §8 names, as `console_look.py` reads them.
MOVING = ("spinner", "skeleton", "bar")


def signed_in_views() -> list[str]:
    """Every view `pages.json` names that a signed-in person reaches."""
    views = json.loads(PAGES.read_text(encoding="utf-8"))["views"]
    return sorted(view["id"] for view in views if view["id"] not in SIGNED_OUT)


def look_problems(record: dict[str, Any], allowed: set[str]) -> list[str]:
    """Every way the record's pages fall short, one line each -- empty when
    every signed-in view was read at both widths and passed every floor."""
    problems: list[str] = []
    if record.get("exit") != 0:
        problems.append(f"the walk exited {record.get('exit')}")
    if "sign_in" in record:
        problems.append(f"the sign-in failed: {record['sign_in']}")
    if record.get("operation_read") is not True:
        problems.append("no operation was read, so the tracker's page was not")
    wanted = signed_in_views()
    if sorted(record.get("views") or []) != wanted:
        problems.append(f"views {sorted(record.get('views') or [])} are not {wanted}")
    read: set[tuple[str, tuple[int, ...]]] = set()
    for page in record.get("pages") or []:
        tag = f"{page.get('view')} at {page.get('viewport')}"
        if "error" in page:
            problems.append(f"{tag}: not read ({page['error']})")
            continue
        read.add((page["view"], tuple(page["viewport"])))
        width, inner = page["scroll"]
        if width > inner:
            problems.append(f"{tag}: scrolls sideways ({width} > {inner})")
        if not page["requests"]:
            problems.append(f"{tag}: the walk read no request at all")
        foreign = sorted(set(page["origins"]) - allowed) + sorted(page.get("foreign") or [])
        if foreign:
            problems.append(f"{tag}: asked another origin {sorted(set(foreign))}")
        if page["violations"]:
            problems.append(f"{tag}: policy violations {page['violations']}")
        if page["unnamed_controls"]:
            problems.append(f"{tag}: unnamed controls {page['unnamed_controls']}")
        rings = page["focus"]
        if len(rings) != TABS:
            problems.append(f"{tag}: {len(rings)} Tabs read, not {TABS}")
        for ring in rings:
            if {key: ring.get(key) for key in RING} != RING:
                problems.append(f"{tag}: Tab landed on {ring.get('tag')} without the ring {ring}")
        if not page.get("title"):
            problems.append(f"{tag}: no title")
    for view in wanted:
        for viewport in VIEWPORTS:
            if (view, viewport) not in read:
                problems.append(f"{view} at {list(viewport)}: never read")
    return problems


def motion_problems(motion: dict[str, Any]) -> list[str]:
    """Reduced motion stops all three moving things; the default keeps each
    moving -- so a reading that saw nothing move is not a pass."""
    problems = []
    for name in MOVING:
        reduced = (motion.get("reduce") or {}).get(name)
        default = (motion.get("no-preference") or {}).get(name)
        if reduced != "none":
            problems.append(f"{name} still animates ({reduced!r}) under reduced motion")
        if default in (None, "", "none"):
            problems.append(f"{name} does not animate by default ({default!r})")
    return problems


@pytest.fixture(scope="module")
def look(control: dict[str, Any], endpoint: str) -> dict[str, Any]:
    """The walk's record: private, live, Session 47's, at the control project's
    console origin, about the deployed commit."""
    path = Path(os.environ.get("APG_CONSOLE_LOOK_RECORD_FILE", ""))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600, f"{path} is not 0600"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert (document.get("session"), document.get("kind"), document.get("mode")) == (
        47,
        "console_look",
        "live",
    ), (document.get("session"), document.get("kind"), document.get("mode"))
    assert document.get("dry") is False
    host = str(urlsplit(endpoint).hostname)
    assert document.get("base") == naming.console_origin(host), document.get("base")
    assert document.get("source_commit") == control["source_commit"], (
        f"the walk names {document.get('source_commit')}, the control project is at "
        f"{control['source_commit']}: a record from another release"
    )
    return document


@pytest.fixture(scope="module")
def allowed(look: dict[str, Any], endpoint: str) -> set[str]:
    """The console's own origin and the relay's -- derived from the control
    project's domain, never read from the record it checks."""
    host = str(urlsplit(endpoint).hostname)
    origins = {naming.console_origin(host), naming.sql_relay_origin(naming.sql_relay_host(host))}
    assert sorted(look.get("allowed_origins") or []) == sorted(origins), look.get("allowed_origins")
    assert look.get("relay") == naming.sql_relay_origin(naming.sql_relay_host(host))
    return origins


def test_the_walk_read_every_signed_in_view_at_both_widths(
    look: dict[str, Any], allowed: set[str]
) -> None:
    """Every signed-in view `pages.json` names, at 390 and 1280, read without
    error after one sign-in, the tracker's page included -- and nothing else
    about the pages fell short (each floor also has its own proof below)."""
    assert look_problems(look, allowed) == []


def test_no_page_scrolls_sideways(look: dict[str, Any]) -> None:
    for page in look["pages"]:
        width, inner = page["scroll"]
        assert width <= inner, (page["view"], page["viewport"], width, inner)


def test_every_request_stayed_on_the_consoles_origins(
    look: dict[str, Any], allowed: set[str]
) -> None:
    """Every request a page attempted -- the policy's refusals included -- went
    to the console's origin or the relay's, and the policy reported nothing."""
    for page in look["pages"]:
        assert page["requests"], (page["view"], "the walk read no request at all")
        assert set(page["origins"]) <= allowed, (page["view"], page["viewport"], page["origins"])
        assert page["foreign"] == [] and page["violations"] == [], (page["view"], page["viewport"])


def test_every_tab_lands_on_the_ring(look: dict[str, Any]) -> None:
    """Four `Tab`s on every page, each on an element drawing the brief's ring."""
    for page in look["pages"]:
        assert len(page["focus"]) == TABS, (page["view"], page["viewport"])
        for ring in page["focus"]:
            assert {key: ring.get(key) for key in RING} == RING, (page["view"], ring)


def test_every_control_has_a_name(look: dict[str, Any]) -> None:
    """The accessibility snapshot of every page names every control in it."""
    for page in look["pages"]:
        assert page["snapshot_lines"] > 0, (page["view"], page["viewport"])
        assert page["unnamed_controls"] == [], (page["view"], page["unnamed_controls"])


def test_reduced_motion_stops_what_moves(look: dict[str, Any]) -> None:
    assert motion_problems(look["motion"]) == []


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
