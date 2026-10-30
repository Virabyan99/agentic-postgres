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
#: `nav.js` and the components into `ui.js` (ADR 0295, D2968); and at Run 5
#: (`~/s47/run5/anchors.py`), when the creation became the tracker's and the
#: Projects pages gained the checklist, the banners and the Notifications feed;
#: and at Run 6 (`~/s47/run6c/anchors.py`), when Connect became three steps and
#: the editor gained its state bar (D2956, D2957); and at Run 7
#: (`~/s47/run7/anchors.py`), when a project's usage before its first sample
#: became an empty state under the project's own heading (one more `h2`); and
#: at Run 9b (`~/s47/run9b/anchors.py`), when the dialog's heading joined
#: `ui.js` (one more `h2`, D3088).
ANCHORS = {
    '"Create your account"': 2, '"Username"': 3, '"Display name"': 1, '"Password"': 3,
    '"Password again"': 1, 'className: "qr"': 1, 'className: "secret"': 3,
    '"Code from your app"': 2, '"Confirm"': 1, '"The next code from your app"': 1,
    '"Sign in"': 4, '"Projects"': 5, '"Sign out"': 1, 'className: "account"': 1,
    'role: "status"': 1,
    'h("textarea"': 1, 'className: "result"': 1, '"Door"': 2, '"Connect"': 6, '"Run"': 1,
    '"Cancel"': 1, '"Disconnect"': 1, 'className: "once"': 2, 'h("h1"': 7, 'h("h2"': 27,
    # Session 47 Run 6 (D2956, D2957): Connect's step 2 and its shown-once box,
    # the client tabs, the editor's Copy as CSV.
    '"Make a new password for the pooled door"': 1, '"Your new password for the pooled door"': 1,
    '"I have saved the password"': 1, 'className: "held"': 1, 'className: "once-done"': 2,
    'role: "tab"': 1, '"Copy as CSV"': 1, '"Copied"': 3,
    # Session 46 (D2918): the journey driver's (`journey_walk.py`).
    '"New organisation"': 4, '"Name"': 5, '"Create"': 1, '"New project"': 5,
    '"Profile"': 1, '"Administrator\'s username"': 1, '"Create project"': 1,
    # Session 47 Run 5 (ADR 0291 amended): the panel's button, the J6 dismissal.
    "\"I've saved it, or I don't need it\"": 1, '"Connect to it"': 2, '"Support bundle"': 1,
    '"Set up your second factor"': 1, '"Something was refused"': 1,
    # Session 47 (ADR 0295): the page titles J11 and J12 read, and the body J11 reads.
    '"Usage"': 4, '"Slowest queries"': 2, '"Monitoring"': 2, '"Plan and usage"': 2,
    '"Notifications"': 4, '"Settings"': 2, 'className: "page-body"': 1,
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


#: The components that make a form control, and how each names it (ui.js).
LABELLED_BY = {
    "field": 'return [h("label", {}, label, input), input];',
    "choice": 'return [h("label", {}, label, select), select];',
    "cellChoice": 'return h("select", { "aria-label": name }, options(list, selected));',
}


def _function(text: str, name: str) -> str:
    found = re.search(rf"^(?:export )?(?:async )?function {name}\(", text, re.MULTILINE)
    assert found, f"no function {name}"
    rest = text[found.start() :]
    return rest[: rest.index("\n}\n") + 2]


def _unlabelled(text: str) -> list[str]:
    """Each control a view script makes by hand (`h("input"`, `h("select"`,
    `h("textarea"`) that nothing names: it must sit directly inside an
    `h("label"` call, be assigned to a name that an `h("label"` call holds, or
    carry an `id` that a label's `htmlFor` names. And every `field(`,
    `choice(` and `cellChoice(` call names its control with a non-empty label."""
    found = []
    for match in re.finditer(r'h\("(input|select|textarea)", \{([^}]*)\}', text):
        before = text[max(0, match.start() - 200) : match.start()]
        if re.search(r'h\("label", \{[^}]*\},\s*$', before):
            continue
        ident = re.search(r'\bid: "([^"]+)"', match.group(2))
        if ident and f'htmlFor: "{ident.group(1)}"' in text:
            continue
        assigned = re.search(r"const (\w+) = (?:[\w.]+\.map\(\([^)]*\) => )?$", before)
        if assigned:
            name = assigned.group(1)
            if re.search(rf'h\("label", \{{[^}}]*\}}[^;]*\b{name}\b', text):
                continue
        found.append(text[match.start() : match.start() + 80])
    for match in re.finditer(r"\b(field|choice|cellChoice)\((\"\"|''|``)", text):
        found.append(text[match.start() : match.start() + 60])
    return found


def test_every_form_control_is_labelled() -> None:
    """The brief's §8: every input, select and textarea has a name a screen
    reader says -- its label, or (a choice in a table row, whose column head
    is its visible label) an `aria-label` naming the row. The components
    label what they make; every view's own control is read by `_unlabelled`.
    The control: the reader finds an unnamed input and an empty label."""
    ui = UI.read_text(encoding="utf-8")
    for name, labelled in LABELLED_BY.items():
        assert labelled in _function(ui, name), name
    modules = _modules()
    for name, text in modules.items():
        if name == "ui.js":
            continue
        assert not _unlabelled(text), (name, _unlabelled(text))
    made = sum(len(re.findall(r'h\("(?:input|select|textarea)", ', t)) for t in modules.values())
    assert made >= 5, made
    assert _unlabelled('const x = h("input", { type: "text" });\nh("p", {}, x);')
    assert _unlabelled('const [, role] = choice("", ROLES, "owner");')
    assert not _unlabelled('h("label", {}, h("input", { type: "radio" }), "A")')


def test_no_state_is_told_by_colour_alone() -> None:
    """The brief's §8: a chip says its state in words (the state word itself);
    a checklist item and a tracker step carry their state as words for a
    screen reader (*done / in progress / to come*) AND a mark whose shape
    differs where its colour does: a tick when done, a dot when in progress, a
    `!` where an operation stopped, a dash when the role needs no factor, a
    dashed ring when unread. The statebar's dot sits beside its state word."""
    ui = UI.read_text(encoding="utf-8")
    assert (
        'className: "chip " + (known ? STATE_CHIPS[state] : "state-unknown") }, value(state))' in ui
    )
    app = APP.read_text(encoding="utf-8")
    for chip in re.finditer(r'h\("span", \{ className: "chip [^"]*" \}, ([^)]*)\)', app):
        assert chip.group(1).strip() not in ('""', ""), chip.group(0)
    tracker = _function(app, "trackerParts")
    assert 'h("span", { className: "sr" }, `, ${words[step.state]}`)' in tracker
    assert 'step.state === DONE ? "✓" : step.state === STOPPED ? "!" : ""' in tracker
    for word in (
        '[DONE]: "done"',
        '[CURRENT]: "in progress"',
        '"to come": "to come"',
        '[STOPPED]: "stopped here"',
    ):
        assert word in tracker, word
    card = _function(app, "checklistCard")
    assert 'h("span", { className: "sr" }, `, ${CHECK_WORDS[state]}`)' in card
    assert 'CHECK_MARKS[state] || ""' in card
    marks = re.search(r"const CHECK_MARKS = \{([^}]*)\};", app)
    assert marks and '[DONE]: "✓"' in marks.group(1) and '[NOT_NEEDED]: "\u2013"' in marks.group(1)
    css = CSS.read_text(encoding="utf-8")
    assert (
        ".current .mark::after {" in css
        and ".checklist li.unread .mark { border-style: dashed; }" in css
    )
    sql = _function(app, "sqlView")
    assert 'h("span", { className: "dot", "aria-hidden": "true" }), state,' in sql


#: The DELETE routes that remove no data a person cannot make again: signing
#: out, a member's membership, an open invitation, an API key. Every other
#: DELETE the console sends -- a project, a branch -- is destructive.
UNDESTRUCTIVE_DELETES = (
    '"/sessions/current"',
    "`/organizations/${org}/members/",
    "`/organizations/${org}/invitations/",
    "`/organizations/${org}/keys/",
)


def _calls(text: str, head: str) -> list[tuple[int, int]]:
    """The span of each `head(` call in `text`, to its matching parenthesis."""
    spans = []
    for found in re.finditer(re.escape(head) + r"\(", text):
        depth, at = 0, found.end() - 1
        for at in range(found.end() - 1, len(text)):
            depth += {"(": 1, ")": -1}.get(text[at], 0)
            if depth == 0:
                break
        spans.append((found.start(), at))
    return spans


def test_every_destructive_action_is_confirmed_by_its_name() -> None:
    """D3088 (ADR 0295 decision 6, the brief's §4 and screen 9): every DELETE
    in `app.js` that removes data -- a project, a branch -- is the `work` of a
    `confirmDialog` whose `name` is the thing's own name; and the component
    opens a modal `<dialog>` named by its heading, its action button disabled
    until `nameConfirmed` and then a busy button, focus handed back to the
    opener on every close, Escape refused while the request is in flight. The
    control: the reader finds a DELETE sent outside a dialog."""
    app = APP.read_text(encoding="utf-8")
    code = "\n".join(line for line in app.splitlines() if not line.lstrip().startswith("//"))
    dialogs = _calls(code, "confirmDialog")
    assert len(dialogs) == 2, dialogs

    def unconfirmed(text: str, spans: list[tuple[int, int]]) -> list[str]:
        found = []
        for delete in re.finditer(r'"DELETE"', text):
            rest = text[delete.end() : delete.end() + 80].lstrip(", ")
            if any(rest.startswith(route) for route in UNDESTRUCTIVE_DELETES):
                continue
            if not any(start < delete.start() < end for start, end in spans):
                found.append(text[delete.start() - 40 : delete.end() + 60])
        return found

    assert not unconfirmed(code, dialogs), unconfirmed(code, dialogs)
    routes = {
        re.search(r'call\("DELETE", `([^`]+)`', code[start:end]).group(1)  # type: ignore[union-attr]
        for start, end in dialogs
    }
    assert routes == {
        "/projects/${key}",
        "/projects/${key}/branches/${encodeURIComponent(branch.name)}",
    }
    names = {re.search(r"\bname: ([\w.]+),", code[start:end]).group(1) for start, end in dialogs}  # type: ignore[union-attr]
    assert names == {"key", "branch.name"}, names
    assert code.count('"DELETE"') == 6
    ui = UI.read_text(encoding="utf-8")
    component = _function(ui, "confirmDialog")
    for part in (
        "const matches = () => nameConfirmed(typed.value, name);",
        '{ busy, className: "danger", disabled: true, enabled: matches }',
        "go.disabled = !matches();",
        "busyButton(action, ",
        'if (go.hasAttribute("aria-busy")) {\n      event.preventDefault();',
        "modal.open(start);",
    ):
        assert part in component, part
    modal = _function(ui, "dialog")
    for part in (
        'h("dialog", { className: "dialog", "aria-labelledby": `${id}-title`',
        'h("h2", { id: `${id}-title` }, title)',
        "element.showModal();",
        "opener.focus();",
    ):
        assert part in modal, part
    # The control: a DELETE of a project sent from a plain button is found.
    planted = 'busyButton("Delete", () => call("DELETE", `/projects/${key}`))'
    assert unconfirmed(planted, []) and not unconfirmed('call("DELETE", "/sessions/current")', [])


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
