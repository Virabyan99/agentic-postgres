"""Every word the console can meet is a sentence with a next action (ADR 0297 decision 3).

Session 47 Run 5 (D2952, D2989, D2996). The set is DERIVED from the modules
that answer or close with each word -- never typed here -- by the method of
the Run 1 inventory (`docs/design/session-47/inventory.md`, `~/s47/run1/
inventory.py`): an AST read of `services/auth-api/app/errors.py` for
`CONTROL_STATUS`'s keys and `OPERATION_ERROR_CODES`, the error documents the
control modules (`control_*.py`) use -- by name, by word, or through an
`errors.*()` helper that answers with one (`errors.malformed()` is the only
door `malformed_request` has) -- the relay's `CLOSE_*` constants with 1000,
1006 and 1011, and the console's own words, the `Refusal` codes `api.js`
makes itself. `services/console/public/messages.js` is read by a regex, the
way `test_console_create` reads it; the wording is run in Node 22
(`NODE_RUNTIME_IMAGE`, `--network none`) against a minimal DOM stand-in.
"""

from __future__ import annotations

# ruff: noqa: E501 -- the embedded JavaScript driver keeps one statement per line.
import ast
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tests.contract.test_image_contracts import LOCK, requires_docker

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

APP = REPO_ROOT / "services" / "auth-api" / "app"
ERRORS = APP / "errors.py"
RELAY = REPO_ROOT / "services" / "sql-relay" / "relay.py"
PUBLIC = REPO_ROOT / "services" / "console" / "public"
MESSAGES = PUBLIC / "messages.js"
NODE = LOCK["NODE_RUNTIME_IMAGE"]
#: The closes a browser meets that the relay does not name: a normal close, a
#: socket that failed or never opened (`pg.js`'s own), and the relay's failure.
BROWSER_CLOSES = {1000, 1006, 1011}


def _constants(path: Path) -> dict[str, Any]:
    """A module's top-level `NAME = literal` assignments (annotated or not);
    a value that is not a literal is kept as its AST node."""
    found: dict[str, Any] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        target = value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        if isinstance(target, ast.Name) and value is not None:
            try:
                found[target.id] = ast.literal_eval(value)
            except ValueError:
                found[target.id] = value
    return found


def _resolve(constants: dict[str, Any], node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return constants[node.id]
    raise AssertionError(f"not a word: {ast.dump(node)}")


def _api_words() -> dict[str, set[str]]:
    """Every word `/v1` can answer, by where it was found."""
    constants = _constants(ERRORS)
    status = constants["CONTROL_STATUS"]
    assert isinstance(status, ast.Dict), "CONTROL_STATUS is no longer a dict literal"
    control_status = {_resolve(constants, key) for key in status.keys if key is not None}
    outcomes = constants["OPERATION_ERROR_CODES"]
    assert isinstance(outcomes, ast.Call) and outcomes.args, "OPERATION_ERROR_CODES moved"
    operation_codes = {_resolve(constants, element) for element in outcomes.args[0].elts}  # type: ignore[attr-defined]
    control = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(APP.glob("control_*.py"))
    )
    assert "errors.ControlRefused(" in control, "the control modules were not read"
    helpers = {
        function.name: {name.id for name in ast.walk(function) if isinstance(name, ast.Name)}
        for function in ast.parse(ERRORS.read_text(encoding="utf-8")).body
        if isinstance(function, ast.FunctionDef)
    }
    by_helper = {
        name
        for helper, names in helpers.items()
        if f"errors.{helper}(" in control
        for name in names
    }
    documents = {
        name: value["error"]
        for name, value in constants.items()
        if isinstance(value, dict) and set(value) == {"error"}
    }
    generic = {
        word
        for name, word in documents.items()
        if f"errors.{name}" in control
        or f'"{word}"' in control
        or f"`{word}`" in control
        or name in by_helper
    }
    return {"CONTROL_STATUS": control_status, "OPERATION_ERROR_CODES": operation_codes,
            "generic": generic}  # fmt: skip


def _console_words() -> set[str]:
    """The words `api.js` makes itself: its own `Refusal` codes."""
    text = (PUBLIC / "api.js").read_text(encoding="utf-8")
    return set(re.findall(r'"([a-z]+(?:_[a-z]+)+)"', text))


def _closes() -> set[int]:
    constants = _constants(RELAY)
    named = {
        value
        for name, value in constants.items()
        if name.startswith("CLOSE_") and isinstance(value, int)
    }
    assert named, "the relay names no close code"
    return named | BROWSER_CLOSES


#: One entry: `  word: {` then its sentence, action and link on the next lines.
ENTRY = re.compile(
    r'^  ([a-z_]+|\d{4}): \{\n    sentence: "([^"]+)",\n    action: (null|"[^"]+"), link: (null|"[^"]*"),\n  \},$',
    re.MULTILINE,
)


def _table(name: str) -> dict[str, tuple[str, str | None, str | None]]:
    text = MESSAGES.read_text(encoding="utf-8")
    block = re.search(rf"^export const {name} = \{{\n(.*?)^\}};$", text, re.MULTILINE | re.DOTALL)
    assert block, f"messages.js holds no {name} table"
    body = block.group(1)
    entries = {
        word: (sentence, None if action == "null" else action.strip('"'),
               None if link == "null" else link.strip('"'))
        for word, sentence, action, link in ENTRY.findall(body)
    }  # fmt: skip
    keys = re.findall(r"^  ([a-z_]+|\d{4}): \{$", body, re.MULTILINE)
    assert sorted(keys) == sorted(entries), (
        f"{name}: an entry is not in the {{sentence, action, link}} shape: "
        f"{sorted(set(keys) - set(entries))}"
    )
    return entries


def test_every_word_the_api_can_answer_has_an_entry() -> None:
    """D2952: the derived set and `REFUSALS`' keys are EQUAL -- a word the
    server can answer with no entry fails, and so does an entry for a word
    nothing answers. The derivation's controls: `malformed_request` is found
    only through `errors.malformed()`, `could_not_determine` only as an
    operation's outcome, and an agent-plane document (`no_such_workflow`) the
    control modules never use is not in the set."""
    found = _api_words()
    words = set().union(*found.values()) | _console_words()
    assert "malformed_request" in found["generic"], "the helper path was not followed"
    assert "could_not_determine" in found["OPERATION_ERROR_CODES"]
    assert "no_such_workflow" not in words and "approval_expired" not in words
    assert "console_unconfigured" in _console_words()
    assert len(set().union(*found.values())) >= 20, sorted(words)
    entries = _table("REFUSALS")
    assert not words - set(entries), f"words without an entry: {sorted(words - set(entries))}"
    assert not set(entries) - words, f"entries for no word: {sorted(set(entries) - words)}"


def test_every_close_code_has_an_entry() -> None:
    """The editor's socket: every code the relay closes with (ADR 0286) and the
    three a browser meets otherwise, each with an entry, and no entry for a
    code nothing closes with."""
    closes = {str(code) for code in _closes()}
    entries = _table("CLOSES")
    assert closes == set(entries), (sorted(closes - set(entries)), sorted(set(entries) - closes))


def test_each_entry_says_what_happened_and_what_to_do() -> None:
    """ADR 0297 decision 3: a sentence that ends; an action for every word but
    a normal close; a link that is a console route or a site path (the site
    paths are held to the site's build by `test_console_pages`). The limit
    refusals lead to the plans (D2954)."""
    entries = {**_table("REFUSALS"), **_table("CLOSES")}
    for word, (sentence, action, link) in entries.items():
        assert sentence[0].isupper() and sentence.endswith("."), word
        assert action or word == "1000", f"{word} names no next action"
        assert link is None or re.fullmatch(r"#/[a-z-]*|/[a-z/-]+/", link), (word, link)
    assert entries["plan_limit_reached"][2] == "/pricing/"
    assert entries["branch_limit_reached"][2] == "/pricing/"
    assert entries["capacity_exhausted"][2] == "#/help"
    assert "nothing was recorded" in entries["plan_limit_reached"][0]


#: A DOM just wide enough for `ui.js` and `messages.js`: elements that keep
#: their children, attributes and properties; text nodes; a body.
DOM = r"""
class Element { constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; } append(...nodes) { this.children.push(...nodes); } setAttribute(name, value) { this.attributes[name] = value; } addEventListener() {} }
globalThis.Node = Element;
globalThis.document = { createElement: (tag) => new Element(tag), createTextNode: (text) => ({ text }), body: new Element("body"), getElementById: () => null };
globalThis.location = { hostname: "control.example.test", hash: "" };
const text = (node) => node.text !== undefined ? node.text : node.children.map(text).join("");
const all = (node, test) => node.children ? [...(test(node) ? [node] : []), ...node.children.flatMap((child) => all(child, test))] : [];
const { REFUSALS, refusal, said, wording } = await import("/console/messages.js");
const { Refusal } = await import("/console/api.js");
const draw = (node) => ({ text: text(node), word: all(node, (n) => n.className === "word").map(text), links: all(node, (n) => n.tag === "a").map((n) => [n.href, text(n)]) });
"""


def _node(tmp_path: Path, driver: str) -> Any:
    directory = tmp_path / "console"
    directory.mkdir(parents=True)
    for script in PUBLIC.glob("*.js"):
        shutil.copy(script, directory / script.name)
    (directory / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
    (directory / "driver.js").write_text(DOM + driver, encoding="utf-8")
    done = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-v", f"{directory}:/console:ro", NODE,
         "node", "/console/driver.js"],
        capture_output=True, text=True, check=False, timeout=120,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@requires_docker
def test_a_refusal_is_drawn_with_its_number_its_action_and_its_word(tmp_path: Path) -> None:
    """The brief's screen 5: the sentence, the next action as a link, and the
    API's word in small type. `plan_limit_reached` names the plan and its
    number from the body the server sent, and links both the site's plans and
    the organisation's Plan page; `branch_limit_reached` names its `limit` and
    `plan` when the route's reader sent them (D2996) and keeps the generic
    sentence for the control set's bare word; a word with no entry is drawn
    with a generic sentence and its word, never dropped; a failure to reach the
    server is said as such."""
    driver = r"""
const plan = new Refusal(409, "plan_limit_reached", { error: "plan_limit_reached", entitlement: "projects_active", limit: 1, plan: "free", message: "x" });
const branch = new Refusal(409, "branch_limit_reached", { error: "branch_limit_reached", limit: 2, plan: "premium" });
const bare = new Refusal(409, "branch_limit_reached", { error: "branch_limit_reached" });
const strange = new Refusal(418, "a_word_nobody_has", null);
console.log(JSON.stringify({
  plan: draw(refusal(plan, { organization: "ORG" })),
  branch: draw(refusal(branch)),
  bare: draw(refusal(bare)),
  strange: draw(refusal(strange)),
  network: draw(refusal(new TypeError("Failed to fetch"))),
  outcome: draw(said("could_not_determine", null)),
  generic: wording("branch_limit_reached", null).sentence === REFUSALS.branch_limit_reached.sentence,
}));
"""
    out = _node(tmp_path, driver)
    assert "Free plan holds 1 project," in out["plan"]["text"], out["plan"]
    assert "nothing was recorded" in out["plan"]["text"]
    assert out["plan"]["word"] == ["plan_limit_reached"]
    assert ["https://example.test/pricing/", "See the plans"] in out["plan"]["links"]
    assert ["#/org/ORG/plan", "Your plan"] in out["plan"]["links"]
    assert "Premium plan allows 2 branches per project" in out["branch"]["text"], out["branch"]
    assert "per project" not in out["bare"]["text"] and out["generic"] is True
    assert out["strange"]["word"] == ["a_word_nobody_has"]
    assert out["strange"]["text"].startswith("The server refused this.")
    assert out["network"]["word"] == [] and "could not be reached" in out["network"]["text"]
    assert out["outcome"]["word"] == ["could_not_determine"]
    assert ["#/help", "Look at the project's state; if it is unclear, ask for help"] in out[
        "outcome"
    ]["links"]
