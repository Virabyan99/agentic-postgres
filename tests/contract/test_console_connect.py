"""Connect and the editor's copies: the server's snippets as served, a password only inside the shown-once panel, a copy control on every value, CSV built in the page.

Session 47 Run 6 (ADR 0295 decisions 6-7, D2956, D2991, D3017).
`services/console/public/copies.js` imports nothing and touches no DOM, so it
runs here in Node 22 (`NODE_RUNTIME_IMAGE`, `--network none`) against the
snippets the server's own `connection_snippets.snippets` builds -- never a
copy of them -- and against texts this test makes. The view's half (where
the filled text is drawn, that every value carries its copy control, that no
console script holds a snippet's text) is read from `app.js`'s Connect section.
"""

from __future__ import annotations

# ruff: noqa: E501 -- the embedded JavaScript drivers keep one statement per line.
import csv
import io
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tests.contract.test_image_contracts import LOCK, requires_docker

from agentic_postgres import REPO_ROOT
from app import connection_snippets

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

PUBLIC = REPO_ROOT / "services" / "console" / "public"
COPIES = PUBLIC / "copies.js"
APP = PUBLIC / "app.js"
NODE = LOCK["NODE_RUNTIME_IMAGE"]
#: Two doors as a deploy records them; the users differ only after a shared prefix.
ENDPOINTS = {
    "enabled": True,
    "pooled": {"host": "pool.slot12.example.test", "port": 5432, "user": "apg_slot12_prod_customer_app",
               "database": "slot12_prod"},
    "direct": {"host": "direct.slot12.example.test", "port": 5432, "user": "apg_slot12_prod_customer_admin",
               "database": "slot12_prod"},
}  # fmt: skip
POOLED_PASSWORD = "PooledMarker-not-a-credential_0"  # noqa: S105 -- a marker, never a value
DIRECT_PASSWORD = "DirectMarker-not-a-credential_1"  # noqa: S105 -- a marker, never a value


def _node(tmp_path: Path, driver: str) -> Any:
    directory = tmp_path / "console"
    directory.mkdir(parents=True)
    shutil.copy(COPIES, directory / "copies.js")
    (directory / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
    (directory / "driver.js").write_text(driver, encoding="utf-8")
    done = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-v", f"{directory}:/console:ro", NODE,
         "node", "/console/driver.js"],
        capture_output=True, text=True, check=False, timeout=120,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def _section(start: str, end: str) -> str:
    """`app.js` from one section marker to the next, its `//` comment lines removed."""
    text = APP.read_text(encoding="utf-8")
    assert text.count(start) == 1 and text.count(end) == 1, (start, end)
    body = text[text.index(start) : text.index(end)]
    return "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("//"))


def _connect() -> str:
    return _section("// -- Connect (", "// -- branches ---")


def _function(body: str, name: str) -> str:
    found = re.search(rf"^(?:async )?function {name}\(.*?^\}}$", body, re.MULTILINE | re.DOTALL)
    assert found, f"no function {name}"
    return found.group(0)


@requires_docker
def test_the_password_fills_only_its_own_doors_placeholders(tmp_path: Path) -> None:
    """Every snippet the server serves, filled for each door in turn: each
    password replaces only placeholders (nothing else moved), the two doors
    never fill the same placeholder (the order does not matter), between them
    they fill every placeholder the server wrote, the pooled door -- the
    application's -- fills at least one in every client that has one, and in a
    URL each password sits after its OWN door's user. A text with no password,
    no placeholder or another door's user is left as it is; a user that is a
    prefix of another is not taken for it."""
    served = connection_snippets.snippets(ENDPOINTS)
    assert list(served) == list(connection_snippets.CLIENTS)
    placeholder = connection_snippets.PASSWORD_PLACEHOLDER
    pooled, direct = ENDPOINTS["pooled"]["user"], ENDPOINTS["direct"]["user"]
    driver = (
        'import { fillPassword } from "/console/copies.js";\n'
        f"const SERVED = {json.dumps(served)};\n"
        f"const PH = {json.dumps(placeholder)};\n"
        f"const DOORS = {{ pooled: {json.dumps(pooled)}, direct: {json.dumps(direct)} }};\n"
        f"const PW = {{ pooled: {json.dumps(POOLED_PASSWORD)}, direct: {json.dumps(DIRECT_PASSWORD)} }};\n"
        "const fill = (text, door) => fillPassword(text, { placeholder: PH, user: DOORS[door], others: Object.values(DOORS).filter((u) => u !== DOORS[door]), password: PW[door] });\n"
        "const out = { clients: {} };\n"
        "for (const [client, text] of Object.entries(SERVED)) {\n"
        "  out.clients[client] = { pooled: fill(text, 'pooled'), direct: fill(text, 'direct'), both: fill(fill(text, 'pooled'), 'direct'), swapped: fill(fill(text, 'direct'), 'pooled') };\n"
        "}\n"
        "out.none = fillPassword('x = <p>', { placeholder: '<p>', user: 'u', others: [], password: '' });\n"
        "out.absent = fillPassword('host=h user=u', { placeholder: '<p>', user: 'u', others: [], password: 'pw' });\n"
        "out.theirs = fillPassword('user=u_admin password=<p>', { placeholder: '<p>', user: 'u', others: ['u_admin'], password: 'pw' });\n"
        "out.prefix = fillPassword('user=u password=<p>', { placeholder: '<p>', user: 'u', others: ['u_admin'], password: 'pw' });\n"
        "out.encoded = fillPassword('postgresql://u:<p>@h/d', { placeholder: '<p>', user: 'u', others: [], password: 'a/b c' });\n"
        "console.log(JSON.stringify(out));\n"
    )
    out = _node(tmp_path, driver)
    for client, text in served.items():
        filled = out["clients"][client]
        written = text.count(placeholder)
        for door, password in (("pooled", POOLED_PASSWORD), ("direct", DIRECT_PASSWORD)):
            assert filled[door].replace(password, placeholder) == text, (client, door)
        assert filled["both"] == filled["swapped"], client
        assert (
            filled["both"].count(POOLED_PASSWORD) + filled["both"].count(DIRECT_PASSWORD) == written
        ), (client, "a placeholder belongs to no door")
        if written:
            assert POOLED_PASSWORD in filled["pooled"], (client, "the pooled door filled nothing")
        for door, password in (("pooled", POOLED_PASSWORD), ("direct", DIRECT_PASSWORD)):
            for line in filled[door].splitlines():
                if password in line and "://" in line:
                    assert f"{ENDPOINTS[door]['user']}:{password}@" in line, (client, door, line)
    assert out["none"] == "x = <p>" and out["absent"] == "host=h user=u"
    assert out["theirs"] == "user=u_admin password=<p>"
    assert out["prefix"] == "user=u password=pw"
    assert out["encoded"] == "postgresql://u:a%2Fb%20c@h/d"


def test_a_snippet_holds_a_password_only_inside_the_shown_once_panel() -> None:
    """D2956, ADR 0295 decision 7: the snippets are drawn as served (the
    placeholder) except in `heldCode`, the one function that fills them, whose
    code sits in the shown-once panel's `held` box; `heldCode` is called only
    after a rotation succeeded, beside the `once` panel that shows the password,
    and both leave together when the person says it is saved."""
    connect = _connect()
    assert connect.count("fillPassword(") == 1, "the password is filled somewhere else too"
    held = _function(connect, "heldCode")
    assert "fillPassword(" in held and 'className: "held"' in held
    plain = _function(connect, "snippetTabs")
    assert "codeBlock(served.snippets[client]," in plain and "password" not in plain
    rotation = _function(connect, "doorPassword")
    assert connect.count("heldCode(") == 2  # its definition and one call
    succeeded = rotation.index('if (final.status !== "succeeded")')
    call = rotation.index("held.replaceChildren(heldCode(served, name, password));")
    panel = rotation.index('h("div", { className: "once" },')
    assert succeeded < panel < call, "the filled code is drawn before the rotation succeeded"
    forget = rotation[
        rotation.index("const forget") : rotation.index(
            'answer.replaceChildren(h("div", { className: "once" },'
        )
    ]
    assert "held.replaceChildren();" in forget
    assert "password = null;" in rotation[rotation.index("} finally {") :]
    # The view itself makes, fills and holds no password: it lays out the boxes.
    view = _function(connect, "connectView")
    for absent in ("newPassword(", "fillPassword(", "heldCode(", "verifier("):
        assert absent not in view, absent


#: A value drawn bare: a `code` element (or `pre`) whose child is not a literal.
BARE = re.compile(r'h\("(?:code|pre|kbd|samp)", \{[^}]*\}, (?!")')


def test_every_value_on_connect_has_a_copy_control() -> None:
    """The person: *"no copy button for the pool string"*. On Connect every
    value is drawn by `inlineCopy` or `codeBlock`, each of which carries a copy
    button (ADR 0295 decision 6); a `code` element there holds only a literal
    word of the page's own prose. Every door part, both connection strings, the
    door's user, the password and each snippet are among the copied values."""
    connect = _connect()
    bare = BARE.findall(connect)
    assert not bare, f"a value on Connect is drawn without its copy control: {bare}"
    for drawn in (
        "inlineCopy(part.value)",
        "inlineCopy(door.user)",
        "codeBlock(connectionString(door), ",
        "codeBlock(connectionString(door, password), ",
        "codeBlock(password, ",
        "codeBlock(served.snippets[client], ",
        "codeBlock(text, ",
    ):
        assert drawn in connect, drawn
    ui = (PUBLIC / "ui.js").read_text(encoding="utf-8")
    code_block = ui[ui.index("export function codeBlock") : ui.index("export function once")]
    inline = ui[ui.index("export function inlineCopy") : ui.index("export function codeBlock")]
    assert (
        "copyButton(text, { target: code })" in code_block
        and "copyButton(text, { target: code })" in inline
    )
    # The control: the pattern sees a value drawn bare, and not the page's own words.
    assert BARE.search('h("code", {}, door.host)') and not BARE.search('h("code", {}, "pg_dump")')


def test_the_connection_string_says_which_clients_take_it() -> None:
    """D3019 (Session 47 Run 9): beside both connection strings on Connect --
    the door's, and the shown-once one with its password -- one line names
    the served clients `copies.js`'s `STRING_TAKEN_BY` holds (measured by
    `test_connection_snippets.py::test_the_consoles_string_is_labelled_for_
    exactly_the_clients_that_take_it`) by their tab names, and points every
    other served client to its own tab. Each name it holds is a served client."""
    text = COPIES.read_text(encoding="utf-8")
    found = re.search(r"^export const STRING_TAKEN_BY = \[([^\]]*)\];$", text, re.MULTILINE)
    assert found, "copies.js names no STRING_TAKEN_BY"
    taken = re.findall(r'"([a-z-]+)"', found.group(1))
    assert taken and set(taken) <= set(connection_snippets.CLIENTS), taken
    connect = _connect()
    note = _function(connect, "stringNote")
    assert "const clients = Object.keys(served.snippets || {});" in note
    assert "clients.filter((client) => STRING_TAKEN_BY.includes(client)).map(clientLabel)" in note
    assert "clients.filter((client) => !STRING_TAKEN_BY.includes(client)).map(clientLabel)" in note
    assert "copy the code from its own tab in step 3" in note
    assert (
        "codeBlock(connectionString(door), { label: `The ${name} door, without its password` }),\n    stringNote(served),"
        in connect
    )
    assert (
        'codeBlock(connectionString(door, password), { label: "The connection string with it", secret: true }),\n        stringNote(served),'
        in connect
    )
    assert connect.count("stringNote(served)") == 3  # its definition and the two strings
    # The string itself is unchanged: J8's and J9's readings parse exactly this.
    built = text[text.index("export function connectionString") :]
    built = built[: built.index("\n}\n")]
    assert built.endswith("?sslmode=verify-full`;") and "sslrootcert" not in built, built


def test_connect_draws_the_clients_the_server_serves() -> None:
    """D2991: one source for a measured text. The tabs are the served
    clients, in the order served, each with the server's `where` line when the
    document carries one; no console script holds a line of any snippet the
    server builds (each of its own lines of 16 characters or more, the door
    values put in by this test)."""
    connect = _connect()
    assert "Object.keys(served.snippets || {})" in _function(connect, "snippetTabs")
    assert "guideLine(served, client)" in _function(connect, "snippetTabs")
    served = connection_snippets.snippets(ENDPOINTS)
    scripts = {path.name: path.read_text(encoding="utf-8") for path in PUBLIC.glob("*.js")}
    lines = {
        line.strip()
        for text in served.values()
        for line in text.splitlines()
        if len(line.strip()) >= 16
    }
    assert len(lines) >= 20, sorted(lines)
    for name, text in scripts.items():
        held = sorted(line for line in lines if line in text)
        assert not held, f"{name} holds the server's snippet text: {held[:3]}"
    where = connection_snippets.where() if hasattr(connection_snippets, "where") else {}
    assert all(set(entry) <= {"file", "install"} for entry in where.values()), where


@requires_docker
def test_the_guide_line_is_read_when_served(tmp_path: Path) -> None:
    """The server's `where` member, when there is one: a file and an install
    line per client, or a sentence; absent, malformed or for another client,
    no line -- never a guess."""
    where = connection_snippets.where() if hasattr(connection_snippets, "where") else {}
    driver = (
        'import { guide } from "/console/copies.js";\n'
        f"const WHERE = {json.dumps(where)};\n"
        "const out = { served: {} };\n"
        "for (const client of Object.keys(WHERE)) out.served[client] = guide({ where: WHERE }, client);\n"
        "out.absent = guide({}, 'psql');\n"
        "out.other = guide({ where: { psql: { file: 'f', install: 'i' } } }, 'prisma');\n"
        "out.sentence = guide({ where: { psql: 'In a terminal.' } }, 'psql');\n"
        "out.malformed = guide({ where: { psql: { file: 3 } } }, 'psql');\n"
        "console.log(JSON.stringify(out));\n"
    )
    out = _node(tmp_path, driver)
    for client, entry in where.items():
        assert out["served"][client] == {"file": entry.get("file"), "install": entry.get("install"),
                                         "text": None}, client  # fmt: skip
    assert out["absent"] is None and out["other"] is None and out["malformed"] is None
    assert out["sentence"] == {"file": None, "install": None, "text": "In a terminal."}


#: Cells a result can carry: a comma, a quote, a line break, a leading space,
#: an empty string, NULL, a plain value and a non-ASCII one.
CELLS = [["a,b", 'say "hi"', "two\nlines", " lead", "", None, "plain", "naïve"]]
COLUMNS = ["comma", "quote", "lines", "space", "empty", "null", "plain", "accent"]


@requires_docker
def test_a_result_is_copied_as_csv(tmp_path: Path) -> None:
    """*Copy as CSV*, built in the page (no library): RFC 4180 quoting -- a
    comma, a quote (doubled), a line break or a surrounding space is quoted --
    CRLF between lines, NULL an empty unquoted field and the empty string an
    empty quoted one (PostgreSQL's COPY convention). Python's own CSV reader
    reads it back to the same cells."""
    driver = (
        'import { csv } from "/console/copies.js";\n'
        f"console.log(JSON.stringify({{ text: csv({json.dumps(COLUMNS)}, {json.dumps(CELLS)}), "
        "header: csv(['n'], []) }));\n"
    )
    out = _node(tmp_path, driver)
    text = out["text"]
    assert text == (
        "comma,quote,lines,space,empty,null,plain,accent\r\n"
        '"a,b","say ""hi""","two\nlines"," lead","",,plain,naïve\r\n'
    ), text
    assert out["header"] == "n\r\n"
    rows = list(csv.reader(io.StringIO(text, newline="")))
    assert rows[0] == COLUMNS
    assert rows[1] == [cell if cell is not None else "" for cell in CELLS[0]]


def test_the_copies_module_is_dom_free_and_keeps_nothing() -> None:
    """`copies.js` imports nothing, touches no DOM, no storage, no network,
    and holds no password of its own: it is handed one."""
    text = COPIES.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
    for absent in ("import ", "document", "window", "localStorage", "sessionStorage", "fetch(",
                   "WebSocket", "navigator", "setTimeout"):  # fmt: skip
        assert absent not in code, absent
    assert "export function fillPassword" in code and "export function csv" in code
