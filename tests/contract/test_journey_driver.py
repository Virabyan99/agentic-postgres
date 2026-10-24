"""JRN-002: the journey's record and the reading that decides it, offline (Session 46).

The driver (`tests/external/browser/journey_walk.py`) needs Chromium, which this
suite does not have; like the console's two walk drivers it is rehearsed by a
script against the console image built from the tree (Run 6's **Done.**,
`--rehearse`, `--leak`, `--plant-foreign`, `--dry`). What runs here is the half
both the driver and the live proofs call -- `journey_record.problems` -- over
records written through the driver's own `Journey`, and the driver's source,
read for the order it takes the steps in.
"""

from __future__ import annotations

import ast
from typing import Any

import pytest
from tests.external.browser import journey_record as jr

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

DRIVER = REPO_ROOT / "tests" / "external" / "browser" / "journey_walk.py"
BASE = "https://control.example.test"
RELAY = "wss://sql.example.test"


def _journey(codes: list[str] | None = None, **members: Any) -> dict[str, Any]:
    """A record written as the driver writes one: each step through
    `Journey.step`, each request through `Journey.saw`."""
    journey = jr.Journey(BASE, RELAY, "https://site.example.test", "rehearsal")
    for code in codes if codes is not None else [code for code, _ in jr.STEPS]:
        journey.step(code, lambda: None)
    for url in (
        f"{BASE}/console/",
        f"{BASE}/api/v1/me",
        f"{RELAY}/pool.example",
        "data:image/svg+xml,x",
    ):
        journey.saw(url)
    journey.record.update(
        exit=0,
        operation_id="6f1d2b7c-9e11-4c3a-9a4e-0b5c6f0e8d0e",
        project_key="slot11-prod",
        organization="0b5c6f0e-8d0e-4c3a-9a4e-3f1d2b7c9e11",
        source_commit="c" * 40,
        site_digest="0" * 64,
        token_file="handoff-token",  # noqa: S106 -- a file's name, not its content
        password_file="password",  # noqa: S106 -- a file's name, not its content
        seed_file="totp-seed",
        string_parameters={"sslmode": "verify-full"},
        views={view: {"read": True, "words": 9} for view in jr.VIEWS},
        support_bundle={"checks": jr.BUNDLE_CHECKS, "aged": jr.BUNDLE_CHECKS, "said": True},
    )
    journey.record.update(members)
    return journey.record


def _driver_steps() -> list[str]:
    """The step codes `journey_walk.py` passes to `.step(...)`, in source order."""
    found = []
    for node in ast.walk(ast.parse(DRIVER.read_text(encoding="utf-8"))):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "step"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append((node.lineno, node.args[0].value))
    return [code for _, code in sorted(found)]


def test_the_rehearsal_reaches_every_step() -> None:
    """A record of every step, in order, each `ok`, on the console's and the
    relay's origins, carrying what the proofs read, reads clean -- full and,
    cut after J5, dry. The driver takes exactly those steps, each once, in
    that order (its source, read). The control: the driver's `Journey` refuses a
    step the journey does not have, and finds a held secret in the record."""
    assert jr.problems(_journey()) == []
    dry = _journey([code for code, _ in jr.DRY_STEPS], dry=True)
    assert jr.problems(dry, dry=True) == []
    assert _driver_steps() == [code for code, _ in jr.STEPS]
    assert [code for code, _ in jr.STEPS][-1] == "j13" and "j09" not in dict(jr.STEPS)
    journey = jr.Journey(BASE, RELAY, "https://site.example.test", "rehearsal")
    with pytest.raises(ValueError):
        journey.step("j99", lambda: None)
    journey.held.append("a-password-the-page-showed")
    journey.record["note"] = "a-password-the-page-showed"
    assert journey.leaks() == 1


def test_a_foreign_request_is_named() -> None:
    """Every request the page attempted, by origin, stays on the console's and
    the relay's (and `data:`, which never leaves the page); a request anywhere
    else is named by its origin. No request at all is a reading that saw
    nothing, never a clean one."""
    planted = _journey()
    planted["origins"].append(jr.origin_of("https://foreign.rehearsal.test/planted.png"))
    assert jr.problems(planted) == [
        "a request left the console's origins: https://foreign.rehearsal.test"
    ]
    assert jr.origin_of("data:image/svg+xml,x") == "data:"
    assert jr.origin_of(f"{RELAY}/pool.example") == RELAY
    blind = _journey(origins=[])
    assert any("saw nothing" in p for p in jr.problems(blind))


def test_a_missing_step_fails_the_record() -> None:
    """A record without J8 names it; a step that failed, steps out of order, a
    dry run's record read as the journey's, a bundle short of the doctor's
    twelve, a view that rendered nothing and a string without verify-full each
    fail -- every problem named, none folded."""
    codes = [code for code, _ in jr.STEPS]
    without = _journey([c for c in codes if c != "j08"])
    assert any(p.startswith("j08 ") and "missing" in p for p in jr.problems(without))
    failed = _journey()
    failed["steps"][5]["outcome"] = "failed"
    assert any("j06 ended 'failed'" in p for p in jr.problems(failed))
    swapped = _journey([*codes[:3], codes[4], codes[3], *codes[5:]])
    assert any("out of order" in p for p in jr.problems(swapped))
    dry = _journey([c for c, _ in jr.DRY_STEPS], dry=True)
    assert jr.problems(dry)  # a dry run is not the journey
    short = _journey(support_bundle={"checks": 11, "aged": 11, "said": True})
    assert any("support bundle" in p for p in jr.problems(short))
    blank = _journey(views={**{v: {"read": True} for v in jr.VIEWS}, "plan": {"read": False}})
    assert any("plan view" in p for p in jr.problems(blank))
    plain = _journey(string_parameters={"sslmode": "require"})
    assert any("verify-full" in p for p in jr.problems(plain))
    assert jr.problems("not a record") == ["the record is a str, not an object"]
