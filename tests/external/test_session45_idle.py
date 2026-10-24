"""Session 45's idle proof: a woken project left untouched is idle-slept (ADR 0289, D2805, D2833).

`USE-LIVE-006` (claim `idle_after_wake_live`) reads the lifecycle record
(`APG_LIFECYCLE_RECORD_FILE`, the same gate the re-earning reads) of slot9-prod
at the deployed commit. From the moment before the export -- the last
recreation before the idle step -- the instrument paused every probe of the
slot and counted its own requests to the slot's routes: none. A recreated
service has no request series at the edge until its next request (D2805), and
before ADR 0289 such a window read the counter `unread` and never slept
(Session 44's attempt 3). The control set requests an idle sleep only over a
window whose every sample READ the counter (ADR 0276, `0008`'s window clause),
so the sleep this record holds -- requested by the reconciler, origin `idle`,
inside the window and two sample intervals -- is the reading of an absent
series as 0 with its witnesses. **No SSH, no process door** (D2174). **None of
these proofs has ever executed.**
"""

# ruff: noqa: F811 -- the imported names are pytest fixtures.

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from tests.external.test_session38_public_lifecycle import (  # noqa: F401 -- fixtures
    control,
    endpoint,
    probe,
    record,
)

pytestmark = [
    pytest.mark.p0,
    pytest.mark.external,
    pytest.mark.requires_environment(
        "APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE", "APG_LIFECYCLE_RECORD_FILE"
    ),
]

#: ADR 0276: the minutes the instrument set and the usage pass's interval.
IDLE_MINUTES = 15
SAMPLE_SECONDS = 300
#: D2855: the window and two intervals (Session 42 measured 1,200.4 s, already
#: past the window and one); also the plan's section 9 stop line.
WITHIN_SECONDS = IDLE_MINUTES * 60 + 2 * SAMPLE_SECONDS


def instant(text: str) -> datetime:
    return datetime.fromisoformat(str(text).replace("Z", "+00:00"))


@pytest.fixture(scope="module")
def idle(record: dict[str, Any]) -> dict[str, Any]:
    """Session 45's record, its idle reading whole."""
    assert record["session"] == 45, f"a Session {record['session']} record, not 45's (D2833)"
    reading = record["observations"]["idle"]
    assert reading.get("minutes") == IDLE_MINUTES, reading.get("minutes")
    assert isinstance(reading.get("quiet"), dict), "the record holds no quiet reading (D2833)"
    assert isinstance(reading.get("requested"), dict), "no idle sleep was requested"
    return reading


def test_the_instrument_made_no_request(record: dict[str, Any], idle: dict[str, Any]) -> None:
    """From before the export to the request the instrument asked the slot's routes
    nothing; every operation it caused in that span was an export -- the last
    recreation -- and the idle step began from that same quiet."""
    quiet = idle["quiet"]
    assert quiet["slot_requests_after_recreation"] == 0, quiet
    assert quiet["before"] == "project.export"
    assert idle["paused_at"] == quiet["from"], (idle["paused_at"], quiet["from"])
    # D2860: the span ends at the request -- the slot's delete comes after it.
    begun, asked = instant(quiet["from"]), instant(idle["requested"]["created_at"])
    since = [op for op in record["operations"] if begun <= instant(op["created_at"]) < asked]
    assert since, "no operation followed the quiet's start: the export was not after it"
    assert {op["type"] for op in since} == {"project.export"}, [op["type"] for op in since]
    assert all(op["status"] == "succeeded" for op in since), [op["status"] for op in since]


def test_the_idle_window_read_zero_not_unread(record: dict[str, Any], idle: dict[str, Any]) -> None:
    """The reconciler asked for the sleep, `origin = idle`, on behalf of the member
    who set the minutes, and it succeeded: the control set's decision, which no
    unread sample in the window can pass. The window began no earlier than the
    last export's finish -- a wake or an export restarts it -- and the product's
    usage of the hour read the counter (not null)."""
    requested = idle["requested"]
    assert requested["origin"] == "idle" and requested["status"] == "succeeded", requested
    last = max(
        instant(op["finished_at"]) for op in record["operations"] if op["type"] == "project.export"
    )
    waited = (instant(requested["created_at"]) - last).total_seconds()
    assert waited >= IDLE_MINUTES * 60 - 1, f"the sleep came {waited} s after the export's finish"
    usage = idle.get("window_usage") or {}
    assert usage.get("project_key") == record["project_key"], usage.get("project_key")
    assert usage.get("requests") is not None, "no sample of the hour read the request counter"


def test_the_sleep_was_requested_in_the_window(idle: dict[str, Any]) -> None:
    """Within the window and two usage intervals of the setting (D2855)."""
    seconds = idle["requested"]["seconds_from_setting"]
    assert 0 < seconds <= WITHIN_SECONDS, (seconds, WITHIN_SECONDS)


def test_this_module_uses_no_ssh() -> None:
    """D2174's rule for a customer proof: nothing here reaches the host but by
    its public names. Read from this file's own text and syntax."""
    text = Path(__file__).read_text(encoding="utf-8")
    for needle in ("para" + "miko", '"s' + 'sh"', "ss" + "h_destination", "ss" + "h-agent"):
        assert needle not in text, needle
    tree = ast.parse(text)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "subprocess" not in imported, imported
