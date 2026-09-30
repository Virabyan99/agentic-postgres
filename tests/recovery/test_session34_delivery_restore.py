"""`REC-EVT-001`: a restored drill carries the undelivered deliveries (D1802).

The outbox is rows in the project's own database, so a restore that works
carries them -- and a delivery that was pending when a cluster died is one a
receiver has not had, so losing it in a restore is losing the event. Session 34
Run 8 gave the drill's `workflow_runs` member a `deliveries` map, the restored
cluster's `connector_delivery` counted by status, or `{"value": null,
"reason": ...}` when the backup predates migration 0036.

**What is compared is the undelivered set AS IT STOOD AT THE TARGET**, not as
it stands now. A delivery pending at the target may be delivered or dead by
the time the live cluster is read, and the drill -- restored to the target --
still holds it pending; comparing today's statuses would race the loop. So the
live side is rebuilt from the row's own times: created at or before the
target, and neither delivered nor dead by then (pending), or dead by then
(dead). The drill's `pending + dead` must EQUAL it.

**The control is the floor**: at least one undelivered delivery must exist at
the target, or the equality compares two zeros. The deployment module
(`tests/deployment/test_session34_connectivity.py`) leaves a dead letter on
purpose, and the sweep collects `tests/deployment` before `tests/recovery`.

**It never executed before the trip.** `test_session32_workflow_restore.py`'s
drill, in its shape: a marker before the target, the target between two
settles, a WAL switch after (D557).
"""

from __future__ import annotations

# ruff: noqa: S608 -- the interpolated values are a uuid this module generated
# and a timestamp the cluster itself returned.
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from tests.recovery.conftest import psql

from agentic_postgres import REPO_ROOT

pytestmark = [
    pytest.mark.p0,
    pytest.mark.recovery,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_B_OUTPUTS"),
]

DRILL_TIMEOUT_SECONDS = 3600
SETTLE_SECONDS = 3


def _wal_switch(document: dict[str, Any]) -> None:
    """Force a segment and wait for the archiver to move (D557), restated from
    `test_session32_workflow_restore.py` rather than imported."""
    before = int(psql(document, "SELECT archived_count FROM pg_stat_archiver"))
    psql(document, "SELECT pg_switch_wal()")
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if int(psql(document, "SELECT archived_count FROM pg_stat_archiver")) != before:
            return
        time.sleep(2)
    pytest.fail(f"archived_count stayed at {before} for 180s after a WAL switch")


def _undelivered_at(document: dict[str, Any], target: str) -> dict[str, int]:
    """Pending and dead AS OF the target, from each row's own times."""
    reading = psql(
        document,
        "SELECT json_build_object("
        "'pending', count(*) FILTER (WHERE (delivered_at IS NULL OR delivered_at > t) "
        "AND (dead_at IS NULL OR dead_at > t)), "
        "'dead', count(*) FILTER (WHERE dead_at <= t)) "
        f"FROM app_private.connector_delivery, (SELECT '{target}'::timestamptz AS t) target "
        "WHERE created_at <= t",
    )
    counts = json.loads(reading)
    return {"pending": int(counts["pending"]), "dead": int(counts["dead"])}


def test_a_restored_drill_carries_the_undelivered_deliveries(
    project_b: dict[str, Any], require_root: None
) -> None:
    """The drill's `deliveries`, pending plus dead, equals the live undelivered
    set as it stood at the target."""
    owner = str(uuid.uuid4())
    marker = f"apg-s34-drill-{owner[:8]}"
    psql(project_b, f"INSERT INTO app.notes (owner_id, title) VALUES ('{owner}', '{marker}')")

    time.sleep(SETTLE_SECONDS)
    target = psql(project_b, "SELECT now()")
    live = _undelivered_at(project_b, target)
    time.sleep(SETTLE_SECONDS)
    psql(project_b, f"DELETE FROM app.notes WHERE owner_id = '{owner}' AND title = '{marker}'")
    _wal_switch(project_b)

    assert live["pending"] + live["dead"] > 0, (
        "the live cluster held no undelivered delivery at the target, so the comparison "
        "below would be two zeros. The deployment module's dead-letter proof leaves one; "
        "run this after it"
    )

    evidence_dir = Path(os.environ.get("APG_EVIDENCE_DIR", REPO_ROOT / "evidence"))
    result = subprocess.run(
        [
            str(REPO_ROOT / "bin" / "restore-test.sh"),
            "--target-time",
            target,
            "--project-dir",
            str(Path(os.environ["APG_PROJECT_B_OUTPUTS"]).parent),
            "--smoke-owner-id",
            owner,
            "--evidence-dir",
            str(evidence_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=DRILL_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, (
        f"the drill exited {result.returncode}\n{result.stdout[-3000:]}\n{result.stderr[-3000:]}"
    )
    documents = sorted(
        evidence_dir.glob(f"restore-drill-{project_b['project']['key']}-*.json"),
        key=lambda path: path.stat().st_mtime,
    )
    assert documents, "the drill exited 0 and wrote no evidence document"
    evidence = json.loads(documents[-1].read_text(encoding="utf-8"))

    member = (evidence.get("workflow_runs") or {}).get("deliveries")
    assert member is not None, f"the drill evidence carries no deliveries: {evidence.keys()}"
    assert member["value"] is not None, (
        f"the restored cluster could not report its deliveries: {member['reason']}. A "
        "backup taken after this trip's deploy carries migration 0036"
    )
    restored = {status: int(count) for status, count in member["value"].items()}
    assert restored.get("pending", 0) == live["pending"], (restored, live, target)
    assert restored.get("dead", 0) == live["dead"], (restored, live, target)
    print(f"undelivered at {target}: live {live}, restored {restored}")
