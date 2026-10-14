"""The backups surface's document (Session 40, ADR 0273, ADR 0195).

`GET /v1/projects/{key}/backups` serves the newest reading the reconciler
recorded, with its age. Three outcomes and a fourth fact -- `window`,
`could_not_determine` with its reason, and `sleeping` -- and a reading that is
missing, stale or undetermined is never served as a window. These proofs drive
`control_service.backups_document`, the one function the route calls;
`test_control_branches` drives the route itself on a cluster.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app import control_service, operations

pytestmark = [pytest.mark.contract, pytest.mark.p0]

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)


def _reading(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "observed_at": NOW - timedelta(minutes=5),
        "repository_status": "ok",
        "archiver_status": "ok",
        "mirror_status": "ok",
        "earliest": datetime(2026, 10, 12, 10, 39, 27, tzinfo=UTC),
        "latest": datetime(2026, 10, 14, 8, 55, tzinfo=UTC),
        "last_full_at": datetime(2026, 10, 12, 10, 39, 26, tzinfo=UTC),
        "sleeping": False,
        "reason": None,
    }
    values.update(changes)
    return values


def test_the_window_is_computed_from_the_readings() -> None:
    """A fresh reading whose three statuses were read is a `window` whose bounds
    are the reading's -- the oldest stop plus a second (D2465) and the
    archiver's last archived moment (D2456) -- with its age and the sentence
    that the top is approximate and a branch at a point is how a restore is
    tested (D2432). A WARN status is still a reading, so still a window."""
    window = control_service.backups_document("slot3-prod", _reading(), NOW)
    assert window["status"] == "window"
    assert window["earliest"] == "2026-10-12T10:39:27+00:00"
    assert window["latest"] == "2026-10-14T08:55:00+00:00"
    assert window["observed_at"] == (NOW - timedelta(minutes=5)).isoformat()
    assert "To test a restore, create a branch" in window["message"]
    warned = control_service.backups_document("slot3-prod", _reading(mirror_status="warn"), NOW)
    assert warned["status"] == "window" and warned["statuses"]["mirror"] == "warn"


@pytest.mark.parametrize(
    ("changes", "named"),
    [
        ({"observed_at": NOW - timedelta(seconds=2 * operations.BACKUP_RECORD_SECONDS + 1)}, "old"),
        ({"repository_status": "unknown"}, "repository"),
        ({"archiver_status": "unknown", "reason": "the archiver did not answer"}, "archiver"),
        ({"mirror_status": "unknown"}, "mirror"),
        ({"earliest": None}, "bounds"),
        ({"latest": None}, "bounds"),
    ],
)
def test_a_stale_reading_is_not_a_window(changes: dict[str, Any], named: str) -> None:
    """ADR 0195: a reading older than two recording intervals, one with a status
    its classifier could not determine, or one without both bounds is
    `could_not_determine` NAMING why -- never a window -- and no bound is served.
    No reading at all is the same. The control: the boundary itself (exactly two
    intervals old) is still a window.

    Goes red if: the age check is dropped or an UNKNOWN status is folded into
    the window."""
    answer = control_service.backups_document("slot3-prod", _reading(**changes), NOW)
    assert answer["status"] == "could_not_determine", answer
    assert named in answer["reason"], answer["reason"]
    assert "earliest" not in answer and "latest" not in answer
    missing = control_service.backups_document("slot3-prod", None, NOW)
    assert missing["status"] == "could_not_determine" and "recorded" in missing["reason"]
    edge = _reading(observed_at=NOW - timedelta(seconds=2 * operations.BACKUP_RECORD_SECONDS))
    assert control_service.backups_document("slot3-prod", edge, NOW)["status"] == "window"


def test_a_sleeping_project_says_its_archiver_is_stopped() -> None:
    """D2182: a sleeping project's archiver is stopped; the surface says so with
    the last point archived before it slept, and serves no window."""
    asleep = control_service.backups_document("slot3-prod", _reading(sleeping=True), NOW)
    assert asleep["status"] == "sleeping"
    assert "archiver is stopped" in asleep["message"]
    assert "2026-10-14T08:55:00+00:00" in asleep["message"]
    assert "earliest" not in asleep
