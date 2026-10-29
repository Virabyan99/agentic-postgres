"""The SQL editor's decisions: only the control API says asleep, doors from the answer, the password to the socket alone.

Session 44 (ADR 0285; D2737, D2738, D2756; rig 44e): `SQL-PAGE-001`'s page half.
`services/console/public/sql.js` imports nothing -- `app.js` passes it `call`
(api.js) and `connect` (pg.js) -- so it runs here in Node 22
(`NODE_RUNTIME_IMAGE`, `--network none`) with a stand-in for each that records
every argument it is given. Every state the control API can answer is walked,
read from `services/auth-api/app/control_states.py` itself.
"""

from __future__ import annotations

# ruff: noqa: E501 -- the embedded JavaScript drivers keep one statement per line.
import ast
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tests.contract.test_console_refusals import DOM
from tests.contract.test_image_contracts import LOCK, requires_docker

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security, requires_docker]

PUBLIC = REPO_ROOT / "services" / "console" / "public"
NODE = LOCK["NODE_RUNTIME_IMAGE"]
STATES_FILE = REPO_ROOT / "services" / "auth-api" / "app" / "control_states.py"
OPEN = {"ready", "updating"}
ASLEEP = {"sleeping", "suspending", "starting"}
MARKER = "pw-marker-not-a-credential"


def _states() -> list[str]:
    """`control_states.STATES`, read from its file -- the set the API answers."""
    tree = ast.parse(STATES_FILE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "STATES":
            return list(ast.literal_eval(node.value))
    raise AssertionError("control_states.STATES not found")


def _node(tmp_path: Path, driver: str) -> Any:
    directory = tmp_path / "console"
    directory.mkdir(parents=True)
    for script in PUBLIC.glob("*.js"):
        shutil.copy(script, directory / script.name)
    (directory / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
    (directory / "driver.js").write_text(driver, encoding="utf-8")
    done = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-v", f"{directory}:/console:ro", NODE,
         "node", "/console/driver.js"],
        capture_output=True, text=True, check=False, timeout=120,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


STANDINS = r"""
import { doors, openDoor, endSentence, runStatement, stateSentence, DEADLINE_SENTENCE, TRUNCATED_SENTENCE } from "/console/sql.js";
const MARKER = "THE_MARKER";
const DOOR = { name: "pooled", host: "pool.slot3.example.test", port: 5432, user: "apg_slot3_prod_customer_app", database: "slot3_prod" };
const recorder = () => { const seen = { calls: [], connects: [], reads: 0 }; return seen; };
const standins = (seen, state) => ({
  call: async (...args) => { seen.calls.push(JSON.stringify(args)); if (state === "__unreadable__") { const e = new Error("x"); e.status = 503; throw e; } return { key: "slot3-prod", state }; },
  connect: async (args) => { seen.connects.push(JSON.stringify(args)); return { opened: true }; },
  readPassword: () => { seen.reads += 1; return MARKER; },
});
"""


def test_an_asleep_project_opens_no_socket(tmp_path: Path) -> None:
    """Every state the control API can answer: a socket opens for `ready` and
    `updating` alone (the control), each other state is a sentence -- and an
    unreadable state too, never a guess."""
    states = _states()
    assert set(states) >= OPEN | ASLEEP | {"unknown"}, states
    driver = (
        STANDINS.replace("THE_MARKER", MARKER)
        + f"const STATES = {json.dumps([*states, '__unreadable__'])};\n"
        + "const out = {};\n"
        + "for (const state of STATES) {\n"
        + "  const seen = recorder();\n"
        + '  const r = await openDoor({ ...standins(seen, state), relay: "wss://sql.example.test", key: "slot3-prod", door: DOOR });\n'
        + "  out[state] = { opened: r.opened, say: r.say || null, connects: seen.connects.length, reads: seen.reads };\n"
        + "}\n"
        + "console.log(JSON.stringify(out));\n"
    )
    out = _node(tmp_path, driver)
    for state in states:
        reading = out[state]
        if state in OPEN:
            assert (reading["opened"], reading["connects"], reading["reads"]) == (True, 1, 1), state
            continue
        assert (reading["opened"], reading["connects"], reading["reads"]) == (False, 0, 0), state
        if state in ASLEEP:
            assert reading["say"] == "This project is asleep. Wake it from Settings, then connect."
        elif state == "unknown":
            assert reading["say"] == "The project's state could not be read; nothing was opened."
        else:  # read, and named (D2768)
            assert reading["say"] == f"The project is {state}; nothing was opened."
    unreadable = out["__unreadable__"]
    assert (unreadable["opened"], unreadable["connects"], unreadable["reads"]) == (False, 0, 0)
    assert unreadable["say"] == "The project's state could not be read; nothing was opened."


def test_a_project_without_doors_shows_no_editor(tmp_path: Path) -> None:
    driver = r"""
import { doors } from "/console/sql.js";
const refusing = async () => { const e = new Error("not_available"); e.status = 409; e.code = "not_available"; throw e; };
const failing = async () => { const e = new Error("authorization_failed"); e.status = 403; e.code = "authorization_failed"; throw e; };
const door = (h) => ({ host: h, port: 5432, user: "u_" + h, database: "d", sslmode: "verify-full", connection_limit: 2 });
const answering = async (method, path) => ({ project: "slot3-prod", pooled: door("pool.x"), direct: door("direct.x"), password: "<password from your file>", path });
const out = { none: await doors(refusing, "control-prod"), some: await doors(answering, "slot3-prod") };
try { await doors(failing, "slot3-prod"); out.other = "swallowed"; } catch (e) { out.other = e.code; }
console.log(JSON.stringify(out));
"""
    out = _node(tmp_path, driver)
    assert out["none"] == {"offered": False}
    assert out["other"] == "authorization_failed"  # any other refusal is not "no doors"
    pooled, direct = out["some"]["doors"]
    assert pooled == {
        "name": "pooled",
        "host": "pool.x",
        "port": 5432,
        "user": "u_pool.x",
        "database": "d",
    }
    assert direct["name"] == "direct" and direct["host"] == "direct.x"
    assert "password" not in json.dumps(out["some"]), "a door carries something besides its address"


def test_the_password_reaches_only_the_socket(tmp_path: Path) -> None:
    """The password is read once, when a door may open, and handed to `connect`
    -- never to the control API. And neither page script sets a deadline of its
    own (D2779): `pg.js`'s 60 s is the editor's."""
    driver = (
        STANDINS.replace("THE_MARKER", MARKER)
        + "const seen = recorder();\n"
        + 'const r = await openDoor({ ...standins(seen, "ready"), relay: "wss://sql.example.test", key: "slot3-prod", door: DOOR });\n'
        + "console.log(JSON.stringify({ opened: r.opened, seen }));\n"
    )
    out = _node(tmp_path, driver)
    assert out["opened"] is True and out["seen"]["reads"] == 1
    assert all(MARKER not in call for call in out["seen"]["calls"]), out["seen"]["calls"]
    (connected,) = (json.loads(c) for c in out["seen"]["connects"])
    assert connected == {
        "relay": "wss://sql.example.test", "host": "pool.slot3.example.test",
        "user": "apg_slot3_prod_customer_app", "database": "slot3_prod", "password": MARKER,
    }  # fmt: skip
    for name in ("app.js", "sql.js"):
        text = (PUBLIC / name).read_text(encoding="utf-8")
        assert "deadlineSeconds" not in text, f"{name} sets a deadline of its own"
    app = (PUBLIC / "app.js").read_text(encoding="utf-8")
    assert 'type: "password", autocomplete: "off"' in app
    assert 'password.value = "";' in app  # the input cleared the moment it is read


def test_every_ending_has_a_sentence(tmp_path: Path) -> None:
    """Since Session 47 Run 6 (D3012, ADR 0297 decision 3) a close of the
    relay's socket is worded by `messages.js`: `sql.js` hands the close code to
    the `closeSentence` the page passes in -- as it is handed `call` and
    `connect` -- on opening a door and during a statement alike, and words none
    itself. A PostgreSQL error keeps its own words and its code. 1009 has no
    entry (D3018: neither this page nor its relay can send it) and, like any
    code with no entry, is still said with its number."""
    driver = (
        DOM
        + r"""
const { endSentence, openDoor, runStatement } = await import("/console/sql.js");
const { closeSentence, CLOSES } = await import("/console/messages.js");
const stand = (code) => `words for ${code}`;
const codes = [4400, 4408, 4413, 4429, 4502, 1000, 1006, 1011, 1009, 4999];
const out = { close: {}, bare: {}, pg: {}, messages: {} };
for (const code of codes) out.close[code] = endSentence({ closeCode: code, message: `the relay closed the session (${code})` }, stand);
for (const code of codes) out.bare[code] = endSentence({ closeCode: code, message: `the relay closed the session (${code})` });
for (const code of codes) out.messages[code] = closeSentence(code);
out.entries = CLOSES;
for (const code of ["08P01", "28P01"]) out.pg[code] = endSentence({ code, message: "SASL authentication failed" }, stand);
out.pg.other = endSentence({ code: "22012", message: "division by zero" }, stand);
const session = (results, error) => ({ async *query() { for (const r of results) yield r; if (error) throw error; } });
const rows = [];
out.capped = await runStatement(session([{ columns: [{ name: "n" }], rows: [["1"]], command: null, notices: [], truncated: true }]), "x", (r) => rows.push(r), stand);
out.rows = rows;
out.deadline = await runStatement(session([], { code: "57014", deadline: true, message: "canceling statement due to user request" }), "x", () => {}, stand);
out.cancelled = await runStatement(session([], { code: "57014", deadline: false, message: "canceling statement due to user request" }), "x", () => {}, stand);
out.closedMidStatement = await runStatement(session([], { closeCode: 4413, message: "x" }), "x", () => {}, stand);
const refused = async () => { const e = new Error("the relay closed the session (4429)"); e.closeCode = 4429; throw e; };
out.opened = await openDoor({ call: async () => ({ state: "ready" }), connect: refused, relay: "wss://r", key: "k", door: { host: "h", user: "u", database: "d" }, readPassword: () => "p", closeSentence: stand });
console.log(JSON.stringify(out));
"""
    )
    out = _node(tmp_path, driver)
    for code in (4400, 4408, 4413, 4429, 4502, 1000, 1006, 1011, 1009, 4999):
        assert out["close"][str(code)] == f"words for {code}", code
        # Without the page's words, pg.js's own message -- never a table of sql.js's.
        assert out["bare"][str(code)] == f"the relay closed the session ({code})", code
    assert out["closedMidStatement"] == "words for 4413"
    assert out["opened"] == {"opened": False, "say": "words for 4429"}
    for code, words in out["entries"].items():
        expected = words["sentence"] + (f" {words['action']}." if words["action"] else "")
        assert out["messages"][code] == expected, code
    assert "1009" not in out["entries"]
    for code in ("1009", "4999"):
        assert out["messages"][code] == (
            f"The editor's connection was closed (code {code}). Connect again."
        )
    # A closed door is never SAID to be asleep (ADR 0195): only the control API
    # knows; 4502's action may say what to do IF it is.
    assert not [code for code, words in out["entries"].items() if "asleep" in words["sentence"]]
    assert out["pg"]["08P01"] == out["pg"]["28P01"] == "The database refused the password."
    assert out["pg"]["other"] == "division by zero (22012)"
    assert (
        out["capped"] is None
        and out["rows"][0]["truncated"] == "Showing the first 1,000 rows; the rest were not read."
    )
    assert out["rows"][0]["columns"] == ["n"]
    assert out["deadline"] == "The statement ran for 60 seconds and was cancelled."
    assert out["cancelled"] == "canceling statement due to user request (57014)"


#: A table of words keyed by a close code (`4408: "..."`), or a branch on one
#: (`closeCode === 4408`, `event.code == 1006`): the shapes a close is worded in.
CLOSE_WORDING = re.compile(
    r"\b(?:4\d{3}|10\d\d)\s*:\s*[\"'`{]|(?:closeCode|\.code)\s*[!=]==?\s*(?:4\d{3}|10\d\d)\b"
)


def test_no_close_is_worded_outside_messages_js() -> None:
    """D3012 (ADR 0297 decision 3): every close code the editor can meet is
    worded in `messages.js`'s CLOSES and nowhere else -- no other console
    script maps a close code to words or branches on one. `pg.js` may NAME a
    close code it makes (its own 1006 error, its 1000 goodbye); it words none."""
    scripts = {path.name: path.read_text(encoding="utf-8") for path in PUBLIC.glob("*.js")}
    for name, text in scripts.items():
        if name == "messages.js":
            continue
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
        found = CLOSE_WORDING.findall(code)
        assert not found, f"{name} words a close code outside messages.js: {found}"
    assert len(CLOSE_WORDING.findall(scripts["messages.js"])) >= 8
    # The controls: the shapes are recognised, a code merely named is not.
    assert CLOSE_WORDING.search('    4408: "The session ended."')
    assert CLOSE_WORDING.search("if (error.closeCode === 4502) say(x);")
    assert not CLOSE_WORDING.search(
        'new PgError("the relay connection failed", { closeCode: 1006 })'
    )
    assert not CLOSE_WORDING.search("socket.close(1000);")


def _relay_seconds(name: str) -> float:
    tree = ast.parse(
        (REPO_ROOT / "services" / "sql-relay" / "relay.py").read_text(encoding="utf-8")
    )
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == name:
            return float(ast.literal_eval(node.value))
    raise AssertionError(f"relay.py names no {name}")


def test_the_session_limits_beside_run_are_the_relays() -> None:
    """The brief's screen 7: the limits are said beside Run, in the numbers the
    relay enforces (ADR 0286: `IDLE_SECONDS`, `TOTAL_SECONDS`) and the
    statement deadline `pg.js` keeps (`STATEMENT_DEADLINE_SECONDS`) -- and the
    4408 close says the same two numbers."""
    idle, total = _relay_seconds("IDLE_SECONDS") / 60, _relay_seconds("TOTAL_SECONDS") / 60
    assert idle == int(idle) and total == int(total), (idle, total)
    messages = (PUBLIC / "messages.js").read_text(encoding="utf-8")
    limits = re.search(r'export const SESSION_LIMITS = "([^"]+)";', messages)
    assert limits, "messages.js holds no SESSION_LIMITS"
    assert f"{int(idle)} idle minutes" in limits.group(
        1
    ) and f"{int(total)} minutes in all" in limits.group(1)
    close = messages[messages.index("  4408: {") : messages.index("  4413: {")]
    assert f"{int(total)} minutes" in close and f"idle for {int(idle)}" in close
    deadline = re.search(
        r"STATEMENT_DEADLINE_SECONDS = (\d+);", (PUBLIC / "pg.js").read_text("utf-8")
    )
    assert deadline and f"after {deadline.group(1)} seconds" in (PUBLIC / "sql.js").read_text(
        "utf-8"
    )
    editor = _editor()
    assert 'h("p", { className: "small muted" }, SESSION_LIMITS, " ", DEADLINE_SENTENCE)' in editor
    assert editor.index("SESSION_LIMITS") > editor.index('const run = busyButton("Run"')


def _editor() -> str:
    text = (PUBLIC / "app.js").read_text(encoding="utf-8")
    start, end = "// -- the SQL editor (", "// -- the router ---"
    assert text.count(start) == 1 and text.count(end) == 1
    return text[text.index(start) : text.index(end)]


def test_the_editor_hides_its_form_while_connected() -> None:
    """D2957 (the person: *"the new-password option is still there even though
    we are already connected"*), ADR 0295 decision 8: the editor's state is
    drawn in ONE place, `showConnected` -- connected, the credentials form is
    hidden and the statement shown; not, the form is the only thing below the
    bar. Every way the session starts or ends goes through it: the connect,
    a refused connect, Disconnect, a close the page did not ask for, and a
    statement that broke the connection. The state bar, with its one status
    line, comes first on the page."""
    editor = _editor()
    shown = editor[editor.index("function showConnected(door, words) {") :]
    shown = shown[: shown.index("\n  }\n")]
    for line in (
        "const connected = door !== null;",
        "connectForm.hidden = connected;",
        "work.hidden = !connected;",
        "disconnect.hidden = !connected;",
        'state.textContent = connected ? "Connected" : "Not connected";',
    ):
        assert line in shown, line
    assert editor.count(".hidden =") == shown.count(".hidden ="), (
        "the state is drawn somewhere else too"
    )
    for start in (
        "showConnected(door, `Connected to the ${door.name} door as ${door.user}.`);",
        "showConnected(null, opened.say);",
        "showConnected(null, closeSentence(event.code));",
        "showConnected(null, failed);",
        'showConnected(null, "Disconnected. ',
    ):
        assert start in editor, start
    frame = editor[editor.index('frame(me, "SQL editor",\n') :]
    assert frame.index("bar,") < frame.index("connectForm,") < frame.index("work,")
    assert 'role: "status", "aria-live": "polite"' in editor
    assert "disconnect, status);" in editor  # the status line sits in the bar


def test_a_creation_refused_on_the_pooled_door_offers_the_direct_door(tmp_path: Path) -> None:
    """D3045 (Session 47 Run 7): only the direct door's role may create, in
    `public`; the pooled role is refused `permission denied for schema public`
    (42501, measured on pinned PostgreSQL 18 at Run 8). The door choice says
    which door creates tables; that refusal -- and only it -- is answered with
    what happened and an offer to connect on the direct door. The same code on
    the direct door, another schema (`app_private`, refused on both doors) or
    another code is not offered it. The offer disconnects and chooses the direct
    door; the password is the person's to enter again -- nothing is filled in
    (ADR 0285) -- and `sql.js` words the refusal exactly as before."""
    driver = (
        DOM
        + r"""
const { needsDirectDoor, DIRECT_DOOR_HINT, CREATE_ON_POOLED } = await import("/console/messages.js");
const { runStatement } = await import("/console/sql.js");
const publicRefusal = { code: "42501", message: "permission denied for schema public" };
const cases = {
  pooledPublic: [publicRefusal, "pooled"],
  directPublic: [publicRefusal, "direct"],
  pooledPrivate: [{ code: "42501", message: "permission denied for schema app_private" }, "pooled"],
  pooledOther: [{ code: "42P07", message: "relation \"notes\" already exists" }, "pooled"],
  pooledNone: [null, "pooled"],
  disconnected: [publicRefusal, null],
};
const out = {};
for (const [name, [error, door]] of Object.entries(cases)) out[name] = needsDirectDoor(error, door);
const refusing = { async *query() { const e = new Error(publicRefusal.message); e.code = publicRefusal.code; throw e; } };
out.said = await runStatement(refusing, "x", () => {}, () => "close");
out.hint = DIRECT_DOOR_HINT;
out.offer = CREATE_ON_POOLED;
console.log(JSON.stringify(out));
"""
    )
    out = _node(tmp_path, driver)
    assert out["pooledPublic"] is True
    for name in ("directPublic", "pooledPrivate", "pooledOther", "pooledNone", "disconnected"):
        assert out[name] is False, name
    assert out["said"] == "permission denied for schema public (42501)"
    assert out["hint"] == "To create tables, connect on the direct door."
    assert out["offer"]["action"] == "Connect on the direct door"
    editor = _editor()
    assert 'h("p", { className: "hint", id: "door-hint" }, DIRECT_DOOR_HINT)' in editor
    assert 'doorChoice.setAttribute("aria-describedby", "door-hint");' in editor
    assert 'h("h2", {}, "Connect the editor"), doorField, passwordField, connectButton' in editor
    assert "if (failed && needsDirectDoor(refused, connectedTo)) {" in editor
    assert "connectedTo = connected ? door.name : null;" in editor
    assert "watching(session.query(text), (error) => { refused = error; })" in editor
    offer = editor[editor.index("const directDoorOffer = () =>") :]
    offer = offer[: offer.index("})));") + 5]
    assert 'doorChoice.value = "direct";' in offer and "closeEditor();" in offer
    assert "password.focus();" in offer and "password.value" not in offer
    # sql.js keeps its protocol: it words the refusal and knows no door.
    sql = (PUBLIC / "sql.js").read_text(encoding="utf-8")
    assert "42501" not in sql and "DirectDoor" not in sql


def test_the_editors_actions_are_busy_buttons_and_its_first_statement_changes_nothing() -> None:
    """D3006: Connect, Run, Cancel and Disconnect are busy buttons (Cancel
    pressable only while a statement runs); the first statement is filled in
    and only reads; results scroll in their own box under a sticky header, with
    their row count, their time and *Copy as CSV*."""
    editor = _editor()
    for name in ("Connect", "Run", "Cancel", "Disconnect"):
        assert f'busyButton("{name}", ' in editor, name
        assert f'button("{name}"' not in editor.replace(f'busyButton("{name}"', ""), name
    assert "enabled: () => running" in editor and "disabled: true" in editor
    first = re.search(r'const FIRST_STATEMENT = "([^"]+)";', editor)
    assert first and re.fullmatch(r"select [a-z_(), ]+;", first.group(1)), first
    assert "value: FIRST_STATEMENT" in editor
    assert 'copyButton(csv(result.columns, result.rows), { label: "Copy as CSV" })' in editor
    assert "rowsWords(result.rows.length)" in editor and "took(milliseconds)" in editor
    css = (PUBLIC / "app.css").read_text(encoding="utf-8")
    assert ".results th { position: sticky; top: 0;" in css
    assert re.search(r"\.results \{[^}]*max-height: \d+px; overflow: auto;", css)
