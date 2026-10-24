"""Session 46's host proofs: `control.sh status` on the deployed host (ADR 0293).

`OPS-CTLSTATUS-002`'s two node ids, run by the sweep as root after its deploys
(claim `control_status_host`). Nothing here writes: `status` is SELECTs only,
`registry` and `slot.sh status` are reads. Each answer is the operator's own
command's, never a hand-built query (D1114).

The control project's deployed document is `APG_CONTROL_OUTPUTS`, the host
manifest `APG_HOST_MANIFEST` -- the op-readable copies the sweep checks.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST",
        "APG_CONTROL_OUTPUTS",
        "APG_HOST_MANIFEST",
    ),
]

#: The states a listed project may read: `control_states.STATES` without
#: `deleted` (a deleted project is counted, never listed). Typed, not imported
#: -- this proof must not share the command's belief.
LISTED_STATES = frozenset(
    {"creating", "ready", "suspending", "sleeping", "starting", "updating", "deleting", "unknown"}
)


def _run(*command: str, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command), stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=timeout, check=False,
    )  # fmt: skip


def _json(*command: str, codes: tuple[int, ...] = (0,)) -> dict[str, Any]:
    done = _run(*command)
    assert done.returncode in codes, (command, done.returncode, done.stderr[-400:])
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def control_key() -> str:
    path = Path(os.environ["APG_CONTROL_OUTPUTS"])
    if not path.is_file():
        pytest.fail(f"APG_CONTROL_OUTPUTS points at {path}, which does not exist")
    return json.loads(path.read_text(encoding="utf-8"))["project"]["key"]


@pytest.fixture(scope="module")
def status(as_root: None, control_key: str) -> dict[str, Any]:
    answer = _json(str(REPO_ROOT / "bin" / "control.sh"), "status", "--json")
    assert answer["control_project"] == control_key, answer["control_project"]
    unread = {k: v for k, v in answer.items() if isinstance(v, dict) and set(v) == {"unread"}}
    assert not unread, unread
    return answer


def test_status_agrees_with_the_registry(status: dict[str, Any]) -> None:
    """Every key the registry reads as present is listed by `status`, in a
    state `control_states` can answer; every key it reads `agrees (deleted)`
    is counted as deleted and listed nowhere. The control: the registry names
    at least the control project, and `status` lists it."""
    registry = _json(str(REPO_ROOT / "bin" / "control.sh"), "registry", "--json")
    outcomes = {o["project"]: o["outcome"] for o in registry["projects"]}
    listed = {p["key"]: p for p in status["projects"]["listed"]}
    present = {key for key, outcome in outcomes.items() if outcome == "agrees"}
    deleted = {key for key, outcome in outcomes.items() if outcome == "deleted"}
    assert status["control_project"] in present and status["control_project"] in listed
    assert present <= set(listed), sorted(present - set(listed))
    assert not deleted & set(listed), sorted(deleted & set(listed))
    assert status["projects"]["deleted"] == len(deleted), (status["projects"], sorted(deleted))
    strange = {key: p["state"] for key, p in listed.items() if p["state"] not in LISTED_STATES}
    assert not strange, strange


def test_status_counts_the_slots(status: dict[str, Any]) -> None:
    """`status` counts the slots as the control set records them; `slot.sh
    status` reads them from the host. After the sweep's deploys, with the
    reconciler's record current, the two counts by state agree."""
    slots = _json(
        str(REPO_ROOT / "bin" / "slot.sh"),
        "status",
        "--host",
        os.environ["APG_HOST_MANIFEST"],
        "--json",
        codes=(0, 6),
    )
    read = Counter(row["state"] for row in slots["slots"])
    assert read, "slot.sh status read no slot: the comparison would be empty"
    assert status["slots"] == dict(read), (status["slots"], dict(read))
