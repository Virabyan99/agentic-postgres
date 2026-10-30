"""Session 47's journey: the creation reloaded, its steps drawn, its start notified.

`CON-RELOAD-001` (claim `console_reload_live`), `CTL-STEPS-002`
(`operation_steps_live`) and `CTL-NOTIFY-003` (`notifications_started_live`) --
ADR 0296, ADR 0297, D2948, D2953, D3104. Read from the journey's record
(`APG_JOURNEY_RECORD_FILE`) that `tests/external/browser/journey_walk.py` wrote
on `slot13-prod` (D2970), and from the lifecycle record that continued its
creation (`APG_LIFECYCLE_RECORD_FILE`, `--from-journey`, D2872), with the same
fixtures as Session 46's journey proofs (`test_session46_journey.py`: private,
live, about the deployed commit, clean by `journey_record.problems`):

* **the reload** (`reload`): J7 reloaded the creation's tracker while it ran;
  the page came back at its own address, `#/operations/<id>`, with its steps
  drawn and the token said to be gone, and the Overview listed the creation
  with its *Follow* link, which the journey then followed to the end;
* **the steps** (`tracker_steps`): at the end the tracker drew every step of
  `project.create` the server's `operation_steps` names, in its order, each
  `done` with the time it took -- a time the console derives only from the step
  log's starts (control set 0011);
* **the start** (the lifecycle's `notifications_after_delete`, the creation's
  organisation listed as the product's CLI lists it): exactly one
  `operation_started` naming the journey's operation by id and type, and its
  `operation_succeeded` naming it too.

The readings are this module's functions (`reload_problems`, `steps_problems`,
`started_problems`), which `tests/contract/test_session47_journey_reading.py`
calls offline (D1114). **No SSH, no process door** (D2174). **None of these
proofs has ever executed.**
"""

# ruff: noqa: F811 -- the imported names are pytest fixtures.

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from tests.external.test_session38_public_lifecycle import control, endpoint  # noqa: F401
from tests.external.test_session46_journey import journey, lifecycle, session_of  # noqa: F401

from agentic_postgres import service_source

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment(
        "APG_CONTROL_OUTPUTS", "APG_JOURNEY_RECORD_FILE", "APG_LIFECYCLE_RECORD_FILE"
    ),
]

#: The first session whose journey reloads its creation (journey_record.RELOAD_SINCE).
RELOAD_SINCE = 47
#: The step state the tracker draws for a step it has finished (`progress.js` DONE).
DONE = "done"


def reload_problems(journey: dict[str, Any]) -> list[str]:
    """What keeps the record's reload from proving the creation survived it."""
    reload = journey.get("reload") if isinstance(journey.get("reload"), dict) else None
    if reload is None:
        return ["the record carries no reload reading"]
    found = []
    if reload.get("tracker") is not True:
        found.append(f"the tracker did not resume after the reload ({reload.get('tracker_error')})")
    if reload.get("address_kept") is not True:
        found.append("the reload left the creation's own address")
    if not (isinstance(reload.get("steps_drawn"), int) and reload["steps_drawn"] > 0):
        found.append(f"the reloaded tracker drew {reload.get('steps_drawn')!r} steps")
    if reload.get("token_said_gone") is not True:
        found.append("the reloaded page did not say the token is gone")
    if reload.get("overview") is not True:
        found.append(f"the Overview did not list the creation ({reload.get('overview_error')})")
    if not (isinstance(reload.get("overview_links"), int) and reload["overview_links"] >= 1):
        found.append(f"the Overview had {reload.get('overview_links')!r} links to the tracker")
    if reload.get("followed_from") != "overview":
        found.append(
            f"the creation was followed from {reload.get('followed_from')!r}, not the Overview"
        )
    return found


def steps_problems(journey: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """What keeps the tracker's last drawing from being every step, in order,
    each done with the time its start in the step log gave it."""
    drawn = journey.get("tracker_steps") if isinstance(journey.get("tracker_steps"), list) else []
    labels = [step["label"] for step in expected["steps"]]
    found = []
    seen = [step.get("label") for step in drawn if isinstance(step, dict)]
    if seen != labels:
        found.append(f"the tracker drew {seen}, not {labels}")
    for step in drawn:
        if not isinstance(step, dict):
            found.append(f"a drawn step is {step!r}")
            continue
        if step.get("state") != DONE:
            found.append(f"{step.get('label')!r} ended {step.get('state')!r}, not {DONE!r}")
        if not str(step.get("time") or "").strip():
            found.append(f"{step.get('label')!r} says no time: its start was not logged")
    return found


def started_problems(journey: dict[str, Any], lifecycle: dict[str, Any]) -> list[str]:
    """What keeps the creation's organisation's notifications from saying it
    started, by its operation, and finished, by the same operation."""
    found = []
    if lifecycle.get("organization_id") != journey.get("organization"):
        found.append("the lifecycle listed another organisation's notifications")
    listed = (lifecycle.get("observations") or {}).get("notifications_after_delete")
    if not isinstance(listed, list):
        return [*found, "the lifecycle recorded no notifications"]
    operation = journey.get("operation_id")
    mine = [n for n in listed if isinstance(n, dict) and n.get("operation_id") == operation]
    started = [n for n in mine if n.get("kind") == "operation_started"]
    if len(started) != 1:
        found.append(f"{len(started)} operation_started notices name the creation, not one")
    for notice in started:
        if notice.get("operation_type") != "project.create":
            found.append(f"the started notice names {notice.get('operation_type')!r}")
    if not any(n.get("kind") == "operation_succeeded" for n in mine):
        found.append("no operation_succeeded notice names the creation")
    return found


def test_the_reload_found_the_creation_again(journey: dict[str, Any]) -> None:
    """CON-RELOAD-001: the tracker resumed at its own address from the API, its
    steps drawn and the token said gone; the Overview listed the creation and
    the journey followed it from there."""
    assert session_of(journey) >= RELOAD_SINCE
    assert reload_problems(journey) == []


def test_the_tracker_drew_every_step_with_its_time(journey: dict[str, Any]) -> None:
    """CTL-STEPS-002: every step the server's `operation_steps` names for a
    creation, in its order, each done with a time from the step log."""
    expected = service_source.load("operation_steps").expected("project.create")
    assert expected is not None
    assert steps_problems(journey, expected) == []


def test_the_creation_was_notified_as_started_by_its_operation(
    journey: dict[str, Any], lifecycle: dict[str, Any]
) -> None:
    """CTL-NOTIFY-003: one `operation_started` names the journey's operation
    by id and type, and its `operation_succeeded` names it too."""
    assert started_problems(journey, lifecycle) == []


def test_this_module_uses_no_ssh() -> None:
    """D2174's rule for a customer proof, read from this file's own text."""
    text = Path(__file__).read_text(encoding="utf-8")
    for needle in ("para" + "miko", '"s' + 'sh"', "ss" + "h_destination", "ss" + "h-agent"):
        assert needle not in text, needle
    imported = {
        alias.name
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "subprocess" not in imported, imported
