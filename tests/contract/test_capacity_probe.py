"""A prepared slot's state directory, read by admission (Session 39, D2341).

`slot.sh`'s preparation writes `bootstrap-state.json` into the state root; the
creation's first deploy writes `outputs.json`. Between the two the directory
holds a provider record and commits nothing -- but `capacity_probe.read`
listed it as a project whose claim it could not read, and `decide` refused
every OTHER project's deploy for it (D2312, exit 12 on Sheet R3a). These
proofs read the repair through the product's own `read` and `decide`, against
the example host's real declaration (`host.example.yaml` declares `slot1-dev`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import (
    REPO_ROOT,
    branch_plan,
    branch_record,
    capacity_probe,
    capacity_reading,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0]

HOST = REPO_ROOT / "host.example.yaml"
SLOT = "slot1-dev"


def _runner(*argv: str, **_: Any) -> None:
    """No Docker: the ceilings and the disk go unread, which decides nothing here."""
    return None


def _state(tmp_path: Path, **directories: dict[str, str]) -> Path:
    root = tmp_path / "projects"
    for key, files in directories.items():
        (root / key).mkdir(parents=True)
        for name, text in files.items():
            (root / key / name).write_text(text, encoding="utf-8")
    root.mkdir(exist_ok=True)
    return root


def _committed_line(reading: capacity_reading.Reading) -> str:
    decision = capacity_reading.decide(
        reading, candidate_key="candidate-dev", candidate_unreclaimable_mb=1,
        candidate_is_deployed=False,
    )  # fmt: skip
    return dict(decision.lines)["committed"]


def test_a_prepared_slot_commits_nothing(tmp_path: Path) -> None:
    """A DECLARED slot with its bootstrap state and no document is `prepared`:
    not unreadable, not summed, and named on the committed line -- so a
    neighbour's deploy is decided on what the host holds, not refused for a
    directory that runs nothing.

    Goes red if: the prepared slot is left in `unreadable` (every deploy exit
    12 again), counted as a claim, or dropped from the line an operator reads."""
    root = _state(tmp_path, **{SLOT: {"bootstrap-state.json": "{}"}})
    reading, _ = capacity_probe.read(HOST, root, runner=_runner)
    assert reading.prepared == (SLOT,), reading.prepared
    assert reading.unreadable == {}, reading.unreadable
    assert reading.committed == {}, reading.committed
    line = _committed_line(reading)
    assert "undetermined" not in line, line
    assert f"{SLOT} prepared, commits nothing" in line, line


def test_an_undeclared_directory_is_still_undetermined(tmp_path: Path) -> None:
    """The control: the SAME directory under a key no slot declares is still a
    claim this command cannot read, and `decide` still fails closed on it
    (ADR 0195). So is a declared slot with neither file, and one whose
    document exists but does not read -- a slot that has been created is a
    project, read like any other."""
    for key, files in (
        ("gamma-dev", {"bootstrap-state.json": "{}"}),
        (SLOT, {}),
        (SLOT, {"bootstrap-state.json": "{}", "outputs.json": "{}"}),
    ):
        root = _state(tmp_path / f"{key}-{len(files)}", **{key: files})
        reading, _ = capacity_probe.read(HOST, root, runner=_runner)
        assert reading.prepared == (), (key, files, reading.prepared)
        assert key in reading.unreadable, (key, files, reading.unreadable)
        assert "undetermined" in _committed_line(reading), (key, files)


def test_the_candidate_slot_is_not_named_prepared(tmp_path: Path) -> None:
    """A creation's own admission excludes the candidate: the slot being
    created is the request, so it is neither a prepared neighbour nor a claim."""
    root = _state(tmp_path, **{SLOT: {"bootstrap-state.json": "{}"}})
    reading, _ = capacity_probe.read(HOST, root, runner=_runner, exclude=SLOT)
    assert reading.prepared == () and reading.unreadable == {}, reading
    assert json.dumps(reading.committed) == "{}"


# ---------------------------------------------------------------------------
# Branches are committed (Session 40, ADR 0271, D2431)
# ---------------------------------------------------------------------------


def _branch(tmp_path: Path, branch: str = "dev", **changes: Any) -> Path:
    """One `branch.json` beside the project root, as `branch-runtime` writes it."""
    values: dict[str, Any] = {
        "project_key": "slot3-prod",
        "branch": branch,
        "state": "ready",
        "operation": "0a7b6f5e-0000-4000-8000-000000000040",
        "requested_point": None,
        "reached_point": "2026-10-14 08:04:58.393241+00",
        "timeline": 2,
        "parent_commit": "b0249ce5667610a45746c6cec89c3eb38457ed70",
        "pool_host": f"{branch}.pool.slot3.agenticpostgresql.com",
        "direct_host": f"{branch}.direct.slot3.agenticpostgresql.com",
        "expires_at": None,
        "expires_for": None,
        "unreclaimable_mb": branch_plan.BRANCH_UNRECLAIMABLE_MB,
        "created_at": "2026-10-14T08:00:00Z",
        "updated_at": "2026-10-14T08:10:00Z",
    }
    values.update(changes)
    path = branch_record.record_path("slot3-prod", branch, root=tmp_path / "branches")
    branch_record.write(path, branch_record.Record(**values))
    return path


def test_a_branch_is_committed(tmp_path: Path) -> None:
    """A recorded branch adds its 192 MiB to the committed total and is NAMED on
    the committed line -- `slot3-prod_dev (branch) 192` -- without being counted
    as a project. A reset's own branch (`exclude_branch`) is the request, not a
    neighbour. With no branch root at all, nothing is added (the control).

    Goes red if: the probe stops reading branch records, a branch is summed as
    zero, or a branch is counted among the projects."""
    root = _state(tmp_path)
    reading, _ = capacity_probe.read(HOST, root, runner=_runner)
    assert reading.branches == {} and reading.unreadable == {}, reading
    assert reading.committed_total_mb == 0

    path = _branch(tmp_path)
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    reading, _ = capacity_probe.read(HOST, root, runner=_runner)
    assert reading.branches == {"slot3-prod_dev": 192}, reading.branches
    assert reading.committed == {} and reading.unreadable == {}, reading
    assert reading.committed_total_mb == 192
    line = _committed_line(reading)
    assert line.startswith("192 MiB across 0 project(s)"), line
    assert "slot3-prod_dev (branch) 192" in line, line

    excluded, _ = capacity_probe.read(HOST, root, runner=_runner, exclude_branch="slot3-prod_dev")
    assert excluded.branches == {} and excluded.committed_total_mb == 0


@pytest.mark.parametrize(
    "damage",
    ["not json", "a member missing", "an unknown state", "a branch directory with no record"],
)
def test_an_unreadable_branch_is_undetermined(tmp_path: Path, damage: str) -> None:
    """ADR 0195: a branch record that cannot be read is a claim this command
    cannot sum, so it is `unreadable` and `decide` refuses -- never a branch
    charged nothing. A readable neighbour in the same root is still summed.

    Goes red if: an unreadable record is folded into "no branch"."""
    root = _state(tmp_path)
    _branch(tmp_path, "qa")
    path = branch_record.record_path("slot3-prod", "dev", root=tmp_path / "branches")
    path.parent.mkdir(parents=True)
    if damage == "not json":
        path.write_text("{", encoding="utf-8")
    elif damage == "a member missing":
        path.write_text(json.dumps({"schema_version": 1, "branch": "dev"}), encoding="utf-8")
    elif damage == "an unknown state":
        good = json.loads(_branch(tmp_path / "x").read_text(encoding="utf-8"))
        path.write_text(json.dumps({**good, "state": "running"}), encoding="utf-8")
    reading, _ = capacity_probe.read(HOST, root, runner=_runner)
    assert "slot3-prod_dev" in reading.unreadable, reading.unreadable
    assert reading.branches == {"slot3-prod_qa": 192}, reading.branches
    assert "undetermined" in _committed_line(reading)
