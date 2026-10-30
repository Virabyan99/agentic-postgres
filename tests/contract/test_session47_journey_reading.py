"""Session 47's journey proofs' readings, held offline (Run 12; D3104, ADR 0296, ADR 0297).

`tests/external/test_session47_journey.py` runs only with the journey's and the
lifecycle's records in the environment. Its three readings are called here on
records built in the test, shaped as `journey_walk.py` (`reload`,
`tracker_steps`) and the lifecycle instrument (`notifications_after_delete`,
the CLI's `--json` listing) write them: a clean record reads clean, and each
planted shortfall is named (D1114: the proof's own functions). The reload's
members are the driver's own (`journey_walk.reload_reading`), read from its
source -- Playwright is not in the venv.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from tests.external import test_session47_journey as proof

from agentic_postgres import REPO_ROOT, service_source

pytestmark = [pytest.mark.contract, pytest.mark.p0]

OPERATION = "5a1d2b7c-9e11-4c3a-9a4e-0b5c6f0e8d0e"
ORG = "31121d7b-1aa3-4206-8f13-d81157c1beaf"
EXPECTED = service_source.load("operation_steps").expected("project.create")


def _journey() -> dict[str, Any]:
    return {
        "session": 47, "operation_id": OPERATION, "organization": ORG,
        "reload": {"tracker": True, "overview": True, "address_kept": True, "steps_drawn": 9,
                   "token_said_gone": True, "overview_links": 1, "followed_from": "overview"},
        "tracker_steps": [{"label": s["label"], "state": "done", "time": "1 min"}
                          for s in EXPECTED["steps"]],
    }  # fmt: skip


def _lifecycle() -> dict[str, Any]:
    def notice(kind: str) -> dict[str, Any]:
        return {"kind": kind, "operation_id": OPERATION, "operation_type": "project.create",
                "project": None, "text": "t"}  # fmt: skip

    return {"organization_id": ORG, "observations": {"notifications_after_delete": [
        notice("operation_started"), notice("operation_succeeded"),
        {"kind": "operation_succeeded", "operation_id": "other", "operation_type": "project.sleep"},
    ]}}  # fmt: skip


def test_the_proofs_read_what_the_driver_writes() -> None:
    """The reload's members are the ones `reload_reading` records, and the
    step state is the console's own `DONE`."""
    walk = (REPO_ROOT / "tests/external/browser/journey_walk.py").read_text(encoding="utf-8")
    reading = walk[
        walk.index("def reload_reading(") : walk.index(
            "\ndef ", walk.index("def reload_reading(") + 1
        )
    ]
    for member in ("tracker", "overview", "address_kept", "steps_drawn", "token_said_gone",
                   "overview_links"):  # fmt: skip
        assert f'reading["{member}"]' in reading or f'"{member}": False' in reading, member
    assert 'reading["followed_from"] = "overview"' in walk
    assert 'record["tracker_steps"] = drawn_steps(page)' in walk
    progress = (REPO_ROOT / "services/console/public/progress.js").read_text(encoding="utf-8")
    assert f'export const DONE = "{proof.DONE}";' in progress


def test_a_clean_journey_reads_clean() -> None:
    assert proof.reload_problems(_journey()) == []
    assert proof.steps_problems(_journey(), EXPECTED) == []
    assert proof.started_problems(_journey(), _lifecycle()) == []


@pytest.mark.parametrize(
    ("member", "value", "expected"),
    [
        ("tracker", False, "did not resume"),
        ("address_kept", False, "own address"),
        ("steps_drawn", 0, "drew 0 steps"),
        ("token_said_gone", False, "token is gone"),
        ("overview", False, "did not list"),
        ("overview_links", 0, "0 links"),
        ("followed_from", "address", "not the Overview"),
    ],
)
def test_each_reload_shortfall_is_named(member: str, value: Any, expected: str) -> None:
    journey = copy.deepcopy(_journey())
    journey["reload"][member] = value
    problems = proof.reload_problems(journey)
    assert any(expected in problem for problem in problems), problems


def test_each_step_shortfall_is_named() -> None:
    swapped = copy.deepcopy(_journey())
    swapped["tracker_steps"][0], swapped["tracker_steps"][1] = (
        swapped["tracker_steps"][1], swapped["tracker_steps"][0],
    )  # fmt: skip
    assert any("the tracker drew" in p for p in proof.steps_problems(swapped, EXPECTED))
    current = copy.deepcopy(_journey())
    current["tracker_steps"][-1]["state"] = "current"
    assert any("not 'done'" in p for p in proof.steps_problems(current, EXPECTED))
    timeless = copy.deepcopy(_journey())
    timeless["tracker_steps"][2]["time"] = ""
    assert any("its start was not logged" in p for p in proof.steps_problems(timeless, EXPECTED))
    assert proof.reload_problems({"session": 47}) == ["the record carries no reload reading"]


def test_each_notice_shortfall_is_named() -> None:
    unstarted = copy.deepcopy(_lifecycle())
    del unstarted["observations"]["notifications_after_delete"][0]
    assert any("0 operation_started" in p for p in proof.started_problems(_journey(), unstarted))
    twice = copy.deepcopy(_lifecycle())
    twice["observations"]["notifications_after_delete"].append(
        twice["observations"]["notifications_after_delete"][0]
    )
    assert any("2 operation_started" in p for p in proof.started_problems(_journey(), twice))
    other = copy.deepcopy(_lifecycle())
    other["organization_id"] = "another"
    assert any("another organisation" in p for p in proof.started_problems(_journey(), other))
    unfinished = copy.deepcopy(_lifecycle())
    del unfinished["observations"]["notifications_after_delete"][1]
    assert any("operation_succeeded" in p for p in proof.started_problems(_journey(), unfinished))
