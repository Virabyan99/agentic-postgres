"""The console look walk's reading, held offline (Session 47 Run 12; D3082, ADR 0295 d9).

`tests/external/test_session47_look.py` (`console_look_live`) runs only with
the walk's record in the environment, so the offline suite never executes it.
Its two readings -- `look_problems` and `motion_problems` -- are called here on
records built in the test, shaped as `tests/external/browser/console_look.py`
writes them: a clean record reads clean, and each planted defect is named
(D1114: the proof's own functions, not a copy). The walk's own constants -- its
widths, its four `Tab`s, the views it skips -- are read from its source, which
cannot be imported here (Playwright is not in the venv), so the walk and its
reader cannot drift apart.
"""

from __future__ import annotations

import ast
import copy
from typing import Any

import pytest
from tests.external import test_session47_look as look_proof

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

WALK = REPO_ROOT / "tests" / "external" / "browser" / "console_look.py"
BASE = "https://control.example.test"
RELAY = "wss://sql.example.test"
ALLOWED = {BASE, RELAY}


def _ring() -> dict[str, Any]:
    return {"tag": "A", "role": None, **look_proof.RING}


def _record() -> dict[str, Any]:
    views = look_proof.signed_in_views()
    pages = [
        {
            "view": view,
            "viewport": list(viewport),
            "url": f"{BASE}/console/#/{view}",
            "title": view.title(),
            "scroll": [viewport[0], viewport[0]],
            "requests": [f"{BASE}/console/app.js", f"{BASE}/api/v1/me"],
            "origins": [BASE],
            "violations": [],
            "snapshot_sha256": "0" * 64,
            "snapshot_lines": 40,
            "unnamed_controls": [],
            "focus": [_ring() for _ in range(look_proof.TABS)],
            "foreign": [],
        }
        for viewport in look_proof.VIEWPORTS
        for view in views
    ]
    return {
        "version": 1, "session": 47, "kind": "console_look", "mode": "live", "base": BASE,
        "dry": False, "exit": 0, "operation_read": True, "views": views, "pages": pages,
        "allowed_origins": sorted(ALLOWED), "relay": RELAY,
        "motion": {"reduce": dict.fromkeys(look_proof.MOVING, "none"),
                   "no-preference": {"spinner": "spin", "skeleton": "pulse", "bar": "slide"}},
    }  # fmt: skip


def _walk_constants() -> dict[str, Any]:
    tree = ast.parse(WALK.read_text(encoding="utf-8"))
    found: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in ("VIEWPORTS", "TABS", "SIGNED_OUT"):
                found[target.id] = ast.literal_eval(node.value)
    return found


def test_the_reader_reads_what_the_walk_writes() -> None:
    """The walk's widths, `Tab`s and skipped views are the reader's; the ring
    the reader asks for is the one the walk's own docstring names; and the
    walk stamps the record the reader's fixture accepts."""
    constants = _walk_constants()
    assert constants == {
        "VIEWPORTS": look_proof.VIEWPORTS,
        "TABS": look_proof.TABS,
        "SIGNED_OUT": look_proof.SIGNED_OUT,
    }, constants
    source = WALK.read_text(encoding="utf-8")
    assert (
        "the 2 px `rgb(31, 79, 163)`" in source and look_proof.RING["color"] == "rgb(31, 79, 163)"
    )
    assert '"version": 1, "session": 47, "kind": "console_look",' in source
    assert '"mode": "rehearsal" if arguments.rehearse else "live"' in source
    for name in look_proof.MOVING:
        assert f"{name}:" in source, name


def test_the_walk_reads_the_probe_owners_own_file() -> None:
    """D3121: the probe owner's file (`~/s37/probe.json`) names its password's
    0600 file, as `sql_walk.py` reads it; the walk reads it from there when the
    probe carries no password, before anything else uses the probe."""
    source = WALK.read_text(encoding="utf-8")
    walk = source[source.index("def walk(") :]
    reads = 'probe["password"] = Path(probe["password_file"]).read_text(encoding="utf-8").strip()'
    assert walk.count(reads) == 1, "the walk does not read the probe's password file"
    assert walk.index(reads) < walk.index('held = [probe["password"], probe["totp_seed"]]')
    sql_walk = (WALK.parent / "sql_walk.py").read_text(encoding="utf-8")
    assert (
        'probe["password"] = Path(probe["password_file"]).read_text(encoding="utf-8").strip()'
        in (sql_walk)
    )


def test_a_clean_record_reads_clean() -> None:
    record = _record()
    assert len(record["pages"]) == 2 * len(look_proof.signed_in_views()) >= 30
    assert look_proof.look_problems(record, ALLOWED) == []
    assert look_proof.motion_problems(record["motion"]) == []


@pytest.mark.parametrize(
    ("defect", "expected"),
    [
        ("overflow", "scrolls sideways"),
        ("foreign", "asked another origin"),
        ("violation", "policy violations"),
        ("unnamed", "unnamed controls"),
        ("ring", "without the ring"),
        ("three_tabs", "Tabs read"),
        ("error", "not read"),
        ("missing", "never read"),
        ("no_operation", "no operation was read"),
        ("exit", "the walk exited"),
        ("no_requests", "no request at all"),
    ],
)
def test_each_shortfall_is_named(defect: str, expected: str) -> None:
    record = copy.deepcopy(_record())
    page = record["pages"][3]
    if defect == "overflow":
        page["scroll"] = [page["scroll"][1] + 1, page["scroll"][1]]
    elif defect == "foreign":
        page["origins"].append("https://third-party.invalid")
    elif defect == "violation":
        page["violations"] = ["img-src"]
    elif defect == "unnamed":
        page["unnamed_controls"] = ["- button"]
    elif defect == "ring":
        page["focus"][2] = {**page["focus"][2], "width": "0px"}
    elif defect == "three_tabs":
        page["focus"] = page["focus"][:3]
    elif defect == "error":
        record["pages"][3] = {
            "view": page["view"],
            "viewport": page["viewport"],
            "error": "Timeout",
        }
    elif defect == "missing":
        del record["pages"][3]
    elif defect == "no_operation":
        record["operation_read"] = False
    elif defect == "exit":
        record["exit"] = 4
    elif defect == "no_requests":
        page["requests"] = []
    problems = look_proof.look_problems(record, ALLOWED)
    assert any(expected in problem for problem in problems), problems


def test_motion_must_stop_under_reduce_and_move_without_it() -> None:
    record = _record()
    moving = copy.deepcopy(record["motion"])
    moving["reduce"]["bar"] = "slide"
    assert look_proof.motion_problems(moving) == [
        "bar still animates ('slide') under reduced motion"
    ]
    still = copy.deepcopy(record["motion"])
    still["no-preference"]["spinner"] = "none"
    assert look_proof.motion_problems(still) == ["spinner does not animate by default ('none')"]
