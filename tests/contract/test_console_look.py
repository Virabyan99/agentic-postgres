"""The console's look: one chip table, static marks, no inline style, counted anchors.

Session 45 (ADR 0288), Session 47 (ADR 0295). `UI-CONSOLE-001`. The state
chips cover every state the control plane names and fail to `unknown`, whose
colours are never `ready`'s (ADR 0195, D2827); the mark and every icon are
static markup in the pages, never built by a script (D2820); no page or script
sets an inline style (the policy has no `'unsafe-inline'`); and every literal
the three browser walk drivers select by -- labels, button names, headings,
`code.secret`, `role=status`, the textarea, `section.result`, the account menu,
the page body -- occurs across the console's modules exactly as often as
`ANCHORS` says. ADR 0295 decision 5 (D2968) superseded the freeze: a commit
that changes one rewrites the driver and re-counts here in the same commit.
"""

from __future__ import annotations

import re

import pytest

from agentic_postgres import REPO_ROOT
from app import control_states

pytestmark = [pytest.mark.contract, pytest.mark.p0]

PUBLIC = REPO_ROOT / "services" / "console" / "public"
APP = PUBLIC / "app.js"
#: Since Session 47 (ADR 0295 decision 3) the components -- the chip table
#: among them -- are `ui.js`'s.
UI = PUBLIC / "ui.js"
CSS = PUBLIC / "app.css"
PAGES = (PUBLIC / "index.html", PUBLIC / "accept.html")

#: Each literal the drivers (`tests/external/browser/console_walk.py`,
#: `sql_walk.py`, and since Session 46 `journey_walk.py`) select by, and how
#: often it occurs across every console module (`public/*.js`) -- re-counted
#: at Session 47 Run 4 (`~/s47/run4/anchors.py`), when the shell moved into
#: `nav.js` and the components into `ui.js` (ADR 0295, D2968).
ANCHORS = {
    '"Create your account"': 2, '"Username"': 3, '"Display name"': 1, '"Password"': 3,
    '"Password again"': 1, 'className: "qr"': 1, 'className: "secret"': 3,
    '"Code from your app"': 2, '"Confirm"': 1, '"The next code from your app"': 1,
    '"Sign in"': 4, '"Projects"': 4, '"Sign out"': 1, 'className: "account"': 1,
    '"New password for the pooled door (customer_app)"': 1, 'role: "status"': 1,
    'h("textarea"': 1, 'className: "result"': 1, '"Door"': 1, '"Connect"': 4, '"Run"': 1,
    '"Cancel"': 1, '"Disconnect"': 1, 'className: "once"': 1, 'h("h1"': 7, 'h("h2"': 13,
    # Session 46 (D2918): the journey driver's (`journey_walk.py`).
    '"New organisation"': 3, '"Name"': 5, '"Create"': 1, '"New project"': 4,
    '"Profile"': 1, '"Administrator\'s username"': 1, '"Create project"': 1,
    '"I have saved it"': 1, '"Connect to it"': 1, '"Support bundle"': 1,
    '"Set up your second factor"': 1, '"Something was refused"': 1,
    # Session 47 (ADR 0295): the page titles J11 and J12 read, and the body J11 reads.
    '"Usage"': 4, '"Slowest queries"': 2, '"Monitoring"': 2, '"Plan and usage"': 2,
    '"Notifications"': 3, '"Settings"': 2, 'className: "page-body"': 1,
}  # fmt: skip


def _modules() -> dict[str, str]:
    """Every console module's text, by name: the shell, the components and the
    views are separate files since Session 47, and an anchor may move between them."""
    found = {path.name: path.read_text(encoding="utf-8") for path in sorted(PUBLIC.glob("*.js"))}
    assert {"app.js", "nav.js", "ui.js"} <= set(found), sorted(found)
    return found


def _state_chips() -> dict[str, str]:
    block = re.search(r"const STATE_CHIPS = \{(.*?)\};", UI.read_text(encoding="utf-8"), re.DOTALL)
    assert block, "ui.js holds no STATE_CHIPS table"
    return dict(re.findall(r"^\s*([a-z]+): \"(state-[a-z]+)\",$", block.group(1), re.MULTILINE))


def _declarations(selector: str) -> dict[str, str]:
    text = CSS.read_text(encoding="utf-8")
    found = re.findall(rf"(?:^|\n)\.{re.escape(selector)} \{{([^}}]*)\}}", text)
    assert len(found) == 1, f"{selector}: {len(found)} rules"
    return dict(part.split(":", 1) for part in found[0].replace(" ", "").split(";") if part)


def test_every_state_has_a_chip() -> None:
    """The table's keys are the control plane's states, each mapped to one of
    the five chip classes, and a value the table does not hold -- or an
    object's own property name -- falls to `state-unknown`."""
    chips = _state_chips()
    assert set(chips) == set(control_states.STATES)
    assert set(chips.values()) == {"state-ready", "state-busy", "state-asleep", "state-gone",
                                   "state-unknown"}  # fmt: skip
    assert chips["ready"] == "state-ready" and chips["unknown"] == "state-unknown"
    text = UI.read_text(encoding="utf-8")
    assert "Object.hasOwn(STATE_CHIPS, state)" in text
    assert '(known ? STATE_CHIPS[state] : "state-unknown")' in text
    for value in chips.values():
        assert _declarations(value), value


def test_an_unknown_state_is_never_ready() -> None:
    """`state-unknown` draws neither `state-ready`'s text colour nor its
    background, by token and by the colour each token holds."""
    tokens = dict(
        re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6});", CSS.read_text(encoding="utf-8"))
    )
    ready, unknown = _declarations("state-ready"), _declarations("state-unknown")
    for prop in ("color", "background"):
        assert ready[prop] != unknown[prop], prop
        assert tokens[ready[prop][6:-1]] != tokens[unknown[prop][6:-1]], prop


def test_the_logo_is_static_markup() -> None:
    """The mark is in each page's own markup, outside `#main`, by presentation
    attributes; no script builds an SVG."""
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        header = text[text.index('<header class="top">') : text.index("</header>")]
        assert header.count("<rect") == 3 and 'class="logo"' in header, page.name
        assert text.index("</header>") < text.index('<main id="main">'), page.name
    for script in PUBLIC.glob("*.js"):
        body = script.read_text(encoding="utf-8")
        assert "createElementNS" not in body and '"svg"' not in body, script.name


def test_no_console_page_carries_a_style_attribute() -> None:
    """No `style=` in either page and no inline style set by any script."""
    for page in PAGES:
        assert not re.search(r"\sstyle\s*=", page.read_text(encoding="utf-8"), re.IGNORECASE)
        assert "<style" not in page.read_text(encoding="utf-8")
    for script in PUBLIC.glob("*.js"):
        body = script.read_text(encoding="utf-8")
        assert not re.search(r"\.style\b|\bstyle\s*:|setAttribute\(\s*[\"']style", body), (
            script.name
        )


def test_a_hidden_field_stays_hidden() -> None:
    """D2853: `label { display: block }` beat the `hidden` attribute, so the
    sign-in view's *Code from your app* field showed before the server asked
    for it (in 1.22.0 too); one rule puts `hidden` back above every display."""
    text = CSS.read_text(encoding="utf-8")
    assert "[hidden] { display: none !important; }" in text
    assert "codeLabel.hidden = true;" in APP.read_text(encoding="utf-8")


def test_the_drivers_anchors_are_unchanged() -> None:
    """Each literal the walk drivers select by occurs across the console's
    modules exactly as often as `ANCHORS` says (re-counted with the drivers,
    ADR 0295 decision 5), each page keeps its one `#main`, and every anchor in
    the table is one a driver file really uses."""
    modules = _modules()
    for anchor, count in ANCHORS.items():
        found = sum(text.count(anchor) for text in modules.values())
        assert found == count, (anchor, found, count)
    for page in PAGES:
        assert page.read_text(encoding="utf-8").count('id="main"') == 1, page.name
    drivers = "".join((REPO_ROOT / "tests" / "external" / "browser" / name).read_text("utf-8")
                      for name in ("console_walk.py", "sql_walk.py",
                                   "journey_walk.py"))  # fmt: skip
    for anchor in ANCHORS:
        literal = re.search(r'"([^"]+)"', anchor)
        if literal and literal.group(1) not in ("qr", "secret", "status", "result", "once"):
            if anchor.startswith('h("'):
                continue
            assert literal.group(1) in drivers, anchor
