"""The telemetry plane is admitted before it starts and charged at its ceilings
(Session 42, ADR 0277, ADR 0221 as amended, D2577).

A store whose use follows its load has no unreclaimable figure to declare, so
its claim is its CEILING: the sum of the four `mem_limit`s in
`infra/telemetry/compose.yaml`. `bin/telemetry.sh up` asks the same `decide`
every deploy asks -- the plane the candidate -- and records the charge in a
state file only after it is admitted; every later admission reads that file
into `Reading.platform`. Present and unreadable is unreadable, never zero.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from agentic_postgres import REPO_ROOT, capacity_probe, capacity_reading, telemetry_plane
from agentic_postgres.host_config import Declared

pytestmark = [pytest.mark.contract, pytest.mark.p0]

#: The OVH host as Session 41 declared it (p6): 7,746 MiB, 2,214 reserved.
DECLARED = Declared(memory_mb=7746, reserve_memory_mb=2214, disk_gb=71, reserve_disk_gb=8)
FOUR = {"alpha-dev": 304, "beta-dev": 304, "control-prod": 304, "slot3-prod": 304}
HOST_EXAMPLE = REPO_ROOT / "host.example.yaml"
PYTHON = (
    str(REPO_ROOT / ".venv/bin/python") if (REPO_ROOT / ".venv/bin/python").exists() else "python3"
)


def _charge() -> int:
    return telemetry_plane.charge_mb(
        yaml.safe_load(telemetry_plane.COMPOSE_PATH.read_text(encoding="utf-8"))
    )


def _reading(**overrides: object) -> capacity_reading.Reading:
    base: dict[str, object] = {
        "declared": DECLARED,
        "mem_total": capacity_reading.Figure.measured(7746),
        "mem_available": capacity_reading.Figure.measured(5089),
        "swap_total": capacity_reading.Figure.measured(0),
        "docker_root_free_gb": capacity_reading.Figure.measured(61),
        "docker_root_total_gb": capacity_reading.Figure.measured(72),
        "committed": dict(FOUR),
        "unreadable": {},
        "ceilings": {},
        "unbounded": (),
    }
    base.update(overrides)
    return capacity_reading.Reading(**base)  # type: ignore[arg-type]


def _decide(reading: capacity_reading.Reading, key: str, mb: int) -> capacity_reading.Decision:
    return capacity_reading.decide(
        reading, candidate_key=key, candidate_unreclaimable_mb=mb, candidate_is_deployed=False
    )


def test_the_plane_is_charged_at_its_ceilings(tmp_path: Path) -> None:
    """The charge is the sum of the model's four `mem_limit`s, exactly; the
    state file `write-state` writes is read by `capacity_probe.read` into
    `Reading.platform`; the committed total carries it and the committed line
    names it. `exclude_platform` is the plane deciding about itself."""
    model = yaml.safe_load(telemetry_plane.COMPOSE_PATH.read_text(encoding="utf-8"))
    limits = [telemetry_plane.memory_mb(s["mem_limit"]) for s in model["services"].values()]
    assert _charge() == sum(limits) == 3552
    projects, state = tmp_path / "projects", tmp_path / "telemetry"
    projects.mkdir()
    state.mkdir()
    done = subprocess.run(
        [PYTHON,
         str(REPO_ROOT / "bin/telemetry.py"), "write-state", "--out-dir", str(state)],
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    recorded = json.loads((state / telemetry_plane.STATE_FILE).read_text("utf-8"))
    assert recorded["charge_mb"] == 3552 and len(recorded["images"]) == 4
    assert (state / telemetry_plane.STATE_FILE).stat().st_mode & 0o777 == 0o644

    def nothing(*_: str, **__: object) -> None:
        return None

    host = REPO_ROOT / "host.example.yaml"
    reading, _ = capacity_probe.read(host, projects, runner=nothing)
    assert reading.platform == {"apg-telemetry": 3552}
    assert reading.committed_total_mb == sum(reading.committed.values()) + 3552
    assert "; apg-telemetry (platform) 3552" in reading.platform_text()
    excluded, _ = capacity_probe.read(host, projects, runner=nothing, exclude_platform=True)
    assert excluded.platform == {}


def test_a_project_is_refused_with_the_charge() -> None:
    """A project that fits without the plane's charge is refused with it --
    the charge is what keeps ClickStack and a project from being admitted
    into the same memory -- and the refusal's committed line names the plane.
    **Control**: no state file (no charge), the same project admitted."""
    candidate = 1000
    admitted = _decide(_reading(), "slot6-prod", candidate)
    assert admitted.outcome == "admitted", admitted.reason
    refused = _decide(_reading(platform={"apg-telemetry": _charge()}), "slot6-prod", candidate)
    assert refused.outcome == "refused" and refused.exit_code == 12, refused.reason
    committed = dict(refused.lines)["committed"]
    assert "apg-telemetry (platform) 3552" in committed, committed


def test_an_unreadable_charge_refuses_rather_than_counting_zero(tmp_path: Path) -> None:
    """A state file that is present and unreadable lands in `unreadable` and
    `decide` refuses on it -- never a plane counted as free (ADR 0195)."""
    projects, state = tmp_path / "projects", tmp_path / "telemetry"
    projects.mkdir()
    state.mkdir()
    (state / telemetry_plane.STATE_FILE).write_text('{"charge_mb": "lots"}\n', encoding="utf-8")

    def nothing(*_: str, **__: object) -> None:
        return None

    reading, _ = capacity_probe.read(REPO_ROOT / "host.example.yaml", projects, runner=nothing)
    assert reading.platform == {}
    assert "apg-telemetry (platform)" in reading.unreadable
    assert (
        _decide(_reading(unreadable=dict(reading.unreadable)), "slot6-prod", 100).outcome
        == "refused"
    )


def test_the_plane_is_refused_when_it_does_not_fit(tmp_path: Path) -> None:
    """`decide` refuses the plane itself when its ceilings do not fit -- and
    `bin/telemetry.sh up` acts on it: exit 12 BEFORE any network, secret or
    container (a fake `docker` records every call; `id` answers 0). The
    reference host.example.yaml declares 1,600 MiB claimable; the plane asks
    3,552."""
    assert (
        _decide(_reading(committed={"a": 4000}), "apg-telemetry (platform)", _charge()).exit_code
        == 12
    )
    bin_dir, log = tmp_path / "bin", tmp_path / "docker.log"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(f'#!/bin/sh\necho "$*" >> {log}\nexit 1\n', encoding="utf-8")
    (bin_dir / "id").write_text("#!/bin/sh\necho 0\n", encoding="utf-8")
    for tool in ("docker", "id"):
        (bin_dir / tool).chmod(0o755)
    done = subprocess.run(
        ["bash", str(REPO_ROOT / "bin/telemetry.sh"), "--host", str(HOST_EXAMPLE), "up"],
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
        env={"PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(tmp_path)},
    )  # fmt: skip
    assert done.returncode == 12, (done.returncode, done.stdout[-600:], done.stderr[-600:])
    assert "refused" in done.stdout
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    # The reading's own daemon queries (`info`, `ps --filter`, `inspect`) may
    # run; nothing that creates or starts may.
    acting = [c for c in calls if c.startswith(("network create", "compose", "run", "volume"))]
    assert acting == [], acting
