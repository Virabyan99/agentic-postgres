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
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
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
    driver = r"""
import { endSentence, runStatement, TRUNCATED_SENTENCE } from "/console/sql.js";
const codes = [4400, 4408, 4413, 4429, 4502, 1009, 1006];
const out = { close: {}, pg: {} };
for (const code of codes) out.close[code] = endSentence({ closeCode: code, message: "x" });
for (const code of ["08P01", "28P01"]) out.pg[code] = endSentence({ code, message: "SASL authentication failed" });
out.pg.other = endSentence({ code: "22012", message: "division by zero" });
const session = (results, error) => ({ async *query() { for (const r of results) yield r; if (error) throw error; } });
const rows = [];
out.capped = await runStatement(session([{ columns: [{ name: "n" }], rows: [["1"]], command: null, notices: [], truncated: true }]), "x", (r) => rows.push(r));
out.rows = rows;
out.deadline = await runStatement(session([], { code: "57014", deadline: true, message: "canceling statement due to user request" }), "x", () => {});
out.cancelled = await runStatement(session([], { code: "57014", deadline: false, message: "canceling statement due to user request" }), "x", () => {});
console.log(JSON.stringify(out));
"""
    out = _node(tmp_path, driver)
    assert out["close"]["4502"] == "The database could not be reached."
    assert out["close"]["4429"] == "Too many editor sessions are open; try again in a minute."
    assert out["close"]["4408"] == "The session ended after 30 minutes, or after 5 idle minutes."
    assert all(out["close"][str(code)] for code in (4400, 4413, 1009))
    assert out["close"]["1006"] == "The relay could not be reached."
    assert "asleep" not in json.dumps(out["close"])  # a closed door is never "asleep" (ADR 0195)
    assert out["pg"]["08P01"] == out["pg"]["28P01"] == "The database refused the password."
    assert out["pg"]["other"] == "division by zero (22012)"
    assert (
        out["capped"] is None
        and out["rows"][0]["truncated"] == "Showing the first 1,000 rows; the rest were not read."
    )
    assert out["rows"][0]["columns"] == ["n"]
    assert out["deadline"] == "The statement ran for 60 seconds and was cancelled."
    assert out["cancelled"] == "canceling statement due to user request (57014)"
