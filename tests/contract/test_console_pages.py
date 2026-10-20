"""The console's pages: calls in the snapshot, rows reachable, no SQL, no storage, no markup.

Session 43 (ADR 0280): `CON-LEDGER-001`'s three page halves and
`CON-SCRAM-001`'s storage half. Read from the files the image bakes
(`services/console/public/`), because they are what a browser runs.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, reality_ledger

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

PUBLIC = REPO_ROOT / "services" / "console" / "public"
SNAPSHOT = REPO_ROOT / "contracts" / "control-openapi.canonical.json"
METHODS = "GET|POST|PUT|PATCH|DELETE"

#: `call(...)` in the views and `send(...)` inside `api.js`: method and path
#: literal (a string or a template), up to the first `+` or `,`.
CALL = re.compile(rf'\b(?:call|send)\(\s*"({METHODS})",\s*(?:"([^"]*)"|`([^`]*)`)')

#: SQL's SHAPE, not its vocabulary: the plan's `\b(select|...|create|...)\s`
#: also matched the page's own sentence "Create your account" (D2696).
SQL = re.compile(
    r"\b(select\s+[\w*,\s]+\s+from|insert\s+into|update\s+\w+\s+set|delete\s+from|"
    r"create\s+(table|role|schema|function|index|view|extension)|"
    r"drop\s+(table|role|schema|function|database)|alter\s+(table|role|system))\b",
    re.IGNORECASE,
)


def _scripts() -> dict[str, str]:
    """Each script's CODE: its full-line `//` comments removed -- the only
    comments these files use (asserted), so a sentence explaining what the
    code never does is not read as the code doing it."""
    scripts = {}
    for path in sorted(PUBLIC.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        assert "/*" not in text, f"{path.name} uses a block comment; this reader removes none"
        lines = [line for line in text.splitlines() if not line.lstrip().startswith("//")]
        scripts[path.name] = "\n".join(lines)
    return scripts


def _called() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for text in _scripts().values():
        for method, plain, template in CALL.findall(text):
            path = plain or re.sub(r"\$\{[^}]*\}", "{x}", template)
            found.add((method, "/v1" + path.split("?", 1)[0]))
    return found


def _operations() -> dict[str, set[str]]:
    paths = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["paths"]
    return {path: {method.upper() for method in operations} for path, operations in paths.items()}


def _matches(path: str, pattern: str) -> bool:
    expression = "^" + re.sub(r"\\\{[^}]*\\\}", "[^/]+", re.escape(pattern)) + "$"
    return re.match(expression, path.replace("{x}", "VALUE")) is not None


def _pages() -> dict[str, Any]:
    return json.loads((PUBLIC / "pages.json").read_text(encoding="utf-8"))


def test_every_called_path_is_in_the_snapshot() -> None:
    """Every call a script makes, and every call `pages.json` lists, is an
    operation the reviewed control snapshot has -- and the two lists agree, so
    `pages.json` (what the guards read) cannot drift from the scripts."""
    operations = _operations()
    called = _called()
    assert len(called) >= 8, f"the extraction found only {sorted(called)}"
    listed = {tuple(entry.split(" ", 1)) for view in _pages()["views"] for entry in view["calls"]}
    for method, path in sorted(called | listed):
        known = [pattern for pattern in operations if _matches(path, pattern)]
        assert known, f"{method} {path} is in no path of the control snapshot"
        assert any(method in operations[pattern] for pattern in known), f"{method} {path}"
    assert {(m, p.replace("{x}", "")) for m, p in called} <= {
        (m, re.sub(r"\{[^}]*\}", "", p)) for m, p in listed
    }, sorted(called - listed)


def test_no_page_names_an_unreachable_row() -> None:
    rows = {row["id"]: row["status"] for row in reality_ledger.load()["rows"]}
    for view in _pages()["views"]:
        for row in view["ledger"]:
            assert rows.get(row) in reality_ledger.REACHABLE, (view["id"], row, rows.get(row))


def test_no_script_holds_sql() -> None:
    for name, text in _scripts().items():
        assert not SQL.search(text), f"{name}: {SQL.search(text).group(0)!r}"
    # The control: the shape is recognised, and the page's own words are not it.
    assert SQL.search("SELECT id FROM app.projects") and SQL.search("drop table x")
    assert not SQL.search("Create your account") and not SQL.search("Delete the project")


def test_no_script_writes_storage() -> None:
    """The session is two HttpOnly cookies no script can read (ADR 0281), and
    a password, a key or a seed lives in one view's variables, never in
    storage a later script could read (D2660)."""
    for name, text in _scripts().items():
        for store in ("localStorage", "sessionStorage", "indexedDB", "document.cookie", "caches."):
            assert store not in text, f"{name} touches {store}"


def test_no_markup_is_built_from_a_value() -> None:
    """Every server value is set as text or a DOM property; no script parses
    markup at all, which is a shorter rule than "only from literals"."""
    for name, text in _scripts().items():
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(",
                     "new Function"):  # fmt: skip
            assert sink not in text, f"{name} uses {sink}"


def test_only_api_js_calls_fetch() -> None:
    callers = sorted(name for name, text in _scripts().items() if "fetch(" in text)
    assert callers == ["api.js"], callers
    api = _scripts()["api.js"]
    assert '"X-Apg-Console"' in api and 'credentials: "same-origin"' in api
    assert 'redirect: "error"' in api
