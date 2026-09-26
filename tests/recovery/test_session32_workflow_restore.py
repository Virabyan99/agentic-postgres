"""`REC-WF-001`: a restored cluster carries the workflow runs (D1529, D1662).

The substrate's state is rows in the project's own database, so a restore
that works carries them -- which is the whole of D1529's argument, and it is
still a claim until a drill has been read. Session 32 Run 6 gave the drill one
member, `workflow_runs`, read with `app_private.workflow_counts()` on the
RESTORED instance, and `{"value": null, "reason": ...}` when that function is
absent -- a backup taken before migration 0034 restores a cluster without it,
and that is a fact about the backup rather than a failed drill (ADR 0195).

**What the member carries is runs by status, and nothing else** (D1699). The
plan wanted `{count, by_status, definitions}`; the reading Run 6 built is
`workflow_counts() ->> 'runs'`, a map of status to count. So this compares the
TOTAL: the drill's runs, summed over statuses, against the live cluster's
count of runs created at or before the target time. Statuses are not compared
-- a run the loop finished after the target is `running` in the drill and
`succeeded` live, and both are right. Definitions are not in the reading and
are not asserted.

**Equality, not `>=`.** A drill holding MORE runs than existed at the target
would be a restore that landed past it, which `REC-PITR-001` exists to catch;
a drill holding fewer lost some. The control is the floor: the live count must
be positive, or the equality compares two zeros and proves nothing -- which is
what it would do if this ran before the trip's runs.

**It never executed before the trip.** One drill, like `test_future_pitr.py`'s,
and in its shape: a marker written before the target so the smoke read has an
owner with a row, the target taken between two settles, and a WAL switch after
a second write so the archive holds the target (D557's stimulus control).
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
    """Force a segment and wait for the archiver to move (D557).

    `test_future_pitr.py`'s helper, restated rather than imported: importing a
    test module would make this module's collection depend on that one's.
    """
    before = int(psql(document, "SELECT archived_count FROM pg_stat_archiver"))
    psql(document, "SELECT pg_switch_wal()")
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if int(psql(document, "SELECT archived_count FROM pg_stat_archiver")) != before:
            return
        time.sleep(2)
    pytest.fail(f"archived_count stayed at {before} for 180s after a WAL switch")


def test_a_restored_drill_carries_the_runs_the_live_cluster_holds(
    project_b: dict[str, Any], require_root: None
) -> None:
    """The drill's `workflow_runs`, summed, equals the live runs at the target."""
    owner = str(uuid.uuid4())
    marker = f"apg-s32-drill-{owner[:8]}"
    psql(project_b, f"INSERT INTO app.notes (owner_id, title) VALUES ('{owner}', '{marker}')")

    time.sleep(SETTLE_SECONDS)
    target = psql(project_b, "SELECT now()")
    live = int(
        psql(
            project_b,
            f"SELECT count(*) FROM app_private.workflow_run WHERE created_at <= '{target}'",
        )
    )
    time.sleep(SETTLE_SECONDS)
    psql(project_b, f"DELETE FROM app.notes WHERE owner_id = '{owner}' AND title = '{marker}'")
    _wal_switch(project_b)

    assert live > 0, (
        "the live cluster held no workflow run at the target, so the comparison below "
        "would be two zeros. This proof reads the runs the trip's workflow proofs left; "
        "run it after them"
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

    member = evidence.get("workflow_runs")
    assert member is not None, f"the drill evidence has no workflow_runs member: {sorted(evidence)}"
    assert member["value"] is not None, (
        f"the restored cluster could not report its runs: {member['reason']}. A backup "
        "taken after this trip's deploy carries migration 0034"
    )
    restored = sum(int(count) for count in member["value"].values())
    assert restored == live, (
        f"the drill restored {restored} runs {member['value']} and the live cluster held "
        f"{live} at the target {target}"
    )
    print(f"workflow runs at {target}: live {live}, restored {restored} {member['value']}")
