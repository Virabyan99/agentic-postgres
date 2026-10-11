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

from agentic_postgres import REPO_ROOT, capacity_probe, capacity_reading

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
