"""A long operation's progress in words: named steps, elapsed and typical time, no percentage.

Session 47 (ADR 0295 decision 3, ADR 0296 decisions 5 and 7; D2949, D2950).
`services/console/public/progress.js` imports nothing and touches no DOM, so it
runs here in Node 22 (`NODE_RUNTIME_IMAGE`, `--network none`), fed operations
shaped as the control mode serves them -- `expected` built by the service's own
`operation_steps.expected` for every type, never retyped -- and a fixed `now`.
The words it returns are checked against numbers this test computes itself
from the same served ranges. The view's half -- the tracker and the status line
draw through it and print no percentage -- is read from `app.js`.
"""

from __future__ import annotations

# ruff: noqa: E501 -- the embedded JavaScript drivers keep one statement per line.
import json
import math
import re
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from tests.contract.test_image_contracts import LOCK, requires_docker

from agentic_postgres import REPO_ROOT
from app import operation_steps

pytestmark = [pytest.mark.contract, pytest.mark.p0, requires_docker]

PUBLIC = REPO_ROOT / "services" / "console" / "public"
PROGRESS = PUBLIC / "progress.js"
NODE = LOCK["NODE_RUNTIME_IMAGE"]
IMPORT = (
    "import { describe, elapsedSeconds, formatDuration, limitText, operationSeconds, "
    'stepStates, typicalRange } from "/console/progress.js";\n'
)
#: The browser's clock in every reading below: a fixed instant, so each
#: elapsed time is a number this test knows.
NOW = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)


def _node(tmp_path: Path, driver: str) -> Any:
    directory = tmp_path / "console"
    directory.mkdir(parents=True)
    shutil.copy(PROGRESS, directory / "progress.js")
    (directory / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
    (directory / "driver.js").write_text(IMPORT + driver, encoding="utf-8")
    done = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-v", f"{directory}:/console:ro", NODE,
         "node", "/console/driver.js"],
        capture_output=True, text=True, check=False, timeout=120,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def _iso(seconds_before_now: float) -> str:
    return (NOW - timedelta(seconds=seconds_before_now)).isoformat()


def _now_ms() -> int:
    return int(NOW.timestamp() * 1000)


def _half_up(value: float) -> int:
    """JavaScript's `Math.round` for a positive number."""
    return math.floor(value + 0.5)


def _range_words(low: float, high: float) -> str:
    """The typical range as this test words it, from the served numbers."""
    if high < 90:
        first, last = max(1, _half_up(low)), max(1, _half_up(high))
        unit = "second"
    else:
        first, last = max(1, _half_up(low / 60)), max(1, _half_up(high / 60))
        unit = "minute"
    if first == last:
        return f"about {first} {unit}{'' if first == 1 else 's'}"
    return f"about {first} to {last} {unit}s"


def _creation(status: str, step: str | None, began: list[tuple[str, float]]) -> dict[str, Any]:
    """A `project.create` as the control mode serves it, its log `began`
    (step, seconds before now) in start order."""
    return {
        "id": "6f1d2b7c-9e11-4c3a-9a4e-0b5c6f0e8d0e",
        "type": "project.create",
        "status": status,
        "step": step,
        "progress": 90,
        "created_at": _iso(1500),
        "started_at": _iso(1490),
        "finished_at": _iso(5) if status in ("succeeded", "failed", "cancelled") else None,
        "steps": [{"step": name, "started_at": _iso(ago)} for name, ago in began],
        "subject": {"name": "notes-app", "profile": "small"},
        "expected": operation_steps.expected("project.create"),
    }


#: A creation at its backup: the eight steps before it begun at these seconds
#: before now (the order the reconciler runs them).
AT_BACKUP = [("allocate", 1490), ("admit", 1489), ("deploy-1", 1488), ("admin", 1424),
             ("ports", 1422), ("deploy-2", 1420), ("unit", 1379), ("backup", 1378)]  # fmt: skip


def test_the_typical_time_is_words_from_the_served_range(tmp_path: Path) -> None:
    """Every type the server describes: the range in minutes or seconds as this
    test computes it from `operation_steps` -- `project.create` reads *about
    23 to 28 minutes* (the brief's number) -- and the limit in minutes; a type
    with no description, or a range not served, reads null, never a guess."""
    served = {kind: operation_steps.expected(kind) for kind in operation_steps.STEPS}
    driver = (
        f"const served = {json.dumps(served)};\n"
        "const out = {};\n"
        "for (const [kind, expected] of Object.entries(served)) out[kind] = [typicalRange(expected), limitText(expected)];\n"
        "out.none = [typicalRange(null), limitText(null)];\n"
        "out.partial = [typicalRange({ typical_seconds: { low: 5 } }), limitText({ bound_seconds: 0 })];\n"
        "console.log(JSON.stringify(out));\n"
    )
    out = _node(tmp_path, driver)
    assert len(served) == 11
    for kind, expected in served.items():
        typical = expected["typical_seconds"]
        words = _range_words(typical["low"], typical["high"])
        assert out[kind] == [words, f"{expected['bound_seconds'] // 60} minutes"], kind
    assert out["project.create"][0] == "about 23 to 28 minutes"
    assert out["branch.create"][1] == "60 minutes" and out["project.sleep"][0] == "about 20 seconds"
    assert out["none"] == [None, None] and out["partial"] == [None, None]


def test_each_step_has_one_state(tmp_path: Path) -> None:
    """A creation at its backup: the seven steps before it *done*, each with
    the seconds to the next step's start; *backup* current with its seconds so
    far; *registry* to come with its typical seconds and no time of its own.
    Succeeded: every step done. Failed at *deploy-1*: the two before it done,
    it *stopped*, the rest to come. Pending and unclaimed: every step to come.
    A step the operation does not name is placed by the furthest step its log
    began. A type the server does not describe has no steps."""
    driver = (
        f"const now = {_now_ms()};\n"
        f"const running = {json.dumps(_creation('running', 'backup', AT_BACKUP))};\n"
        f"const done = {json.dumps(_creation('succeeded', 'registry', [*AT_BACKUP, ('registry', 6)]))};\n"
        f"const failed = {json.dumps(_creation('failed', 'deploy-1', AT_BACKUP[:3]))};\n"
        f"const pending = {json.dumps(_creation('pending', None, []))};\n"
        f"const unnamed = {json.dumps(_creation('running', None, AT_BACKUP[:5]))};\n"
        'const unknown = { ...running, type: "project.mystery", expected: null };\n'
        "console.log(JSON.stringify({ running: stepStates(running, now), done: stepStates(done, now), failed: stepStates(failed, now), pending: stepStates(pending, now), unnamed: stepStates(unnamed, now), unknown: stepStates(unknown, now) }));\n"
    )
    out = _node(tmp_path, driver)
    names = [step for step, _ in operation_steps.STEPS["project.create"]]
    labels = dict(operation_steps.STEPS["project.create"])
    running = out["running"]
    assert [s["step"] for s in running] == names
    assert [s["label"] for s in running] == [labels[n] for n in names]
    assert [s["state"] for s in running] == ["done"] * 7 + ["current", "to come"]
    began = dict(AT_BACKUP)
    for index, step in enumerate(running[:7]):
        assert step["seconds"] == began[names[index]] - began[names[index + 1]], step
        assert step["started_at"] == _iso(began[names[index]])
    assert running[7]["seconds"] == 1378 and running[7]["state"] == "current"
    assert running[8]["seconds"] is None and running[8]["started_at"] is None
    assert (
        running[8]["typical_seconds"] == operation_steps.STEP_SECONDS["project.create"]["registry"]
    )
    assert [s["state"] for s in out["done"]] == ["done"] * 9
    assert out["done"][8]["seconds"] == 1  # registry began 6 s before now, finished 5 s before
    assert [s["state"] for s in out["failed"]] == ["done", "done", "stopped"] + ["to come"] * 6
    assert out["failed"][2]["seconds"] == 1488 - 5
    assert [s["state"] for s in out["pending"]] == ["to come"] * 9
    assert [s["state"] for s in out["unnamed"]] == ["done"] * 4 + ["current"] + ["to come"] * 4
    assert out["unknown"] == []


def test_durations_and_elapsed_times(tmp_path: Path) -> None:
    """Durations are whole seconds under a minute, then minutes, then hours;
    anything that is not a duration is null, never 0 (ADR 0195). An elapsed
    time that cannot be read is null; one the browser's clock puts in the
    future is 0. The whole operation runs from its start to its finish."""
    running = _creation("running", "backup", AT_BACKUP)
    finished = _creation("succeeded", "registry", AT_BACKUP)
    driver = (
        f"const now = {_now_ms()};\n"
        'const durations = [0, 45, 59.4, 59.6, 89, 840, 3599, 3600, 3900, -1, NaN, Infinity, "60", null].map(formatDuration);\n'
        f'const elapsed = [elapsedSeconds("{_iso(90)}", now), elapsedSeconds("not a time", now), elapsedSeconds("{_iso(-30)}", now), elapsedSeconds(null, now), elapsedSeconds("{_iso(90)}", "{_iso(30)}")];\n'
        f"const whole = [operationSeconds({json.dumps(running)}, now), operationSeconds({json.dumps(finished)}, now)];\n"
        "console.log(JSON.stringify({ durations, elapsed, whole }));\n"
    )
    out = _node(tmp_path, driver)
    assert out["durations"] == ["0 s", "45 s", "59 s", "1 min", "1 min", "14 min", "1 h", "1 h",
                                "1 h 5 min", None, None, None, None, None]  # fmt: skip
    assert out["elapsed"] == [90, None, 0, None, 60]
    assert out["whole"] == [1490, 1485]


def test_the_status_line_names_the_step_and_never_a_percentage(tmp_path: Path) -> None:
    """D2949's finding (*"only backup (90%)"*): the line names the step in the
    customer's words, its place, the time so far and the usual time -- and
    never the served `progress`, though the operation carries 90. A finished
    operation says how long it took. The view draws the tracker and every
    status line through these functions, and no percentage is built in it."""
    driver = (
        f"const now = {_now_ms()};\n"
        f"const running = {json.dumps(_creation('running', 'backup', AT_BACKUP))};\n"
        f"const done = {json.dumps(_creation('succeeded', 'registry', AT_BACKUP))};\n"
        'const bare = { status: "running", step: "deploy", progress: 40, expected: null };\n'
        "console.log(JSON.stringify([describe(running, now), describe(done, now), describe(bare, now)]));\n"
    )
    running, done, bare = _node(tmp_path, driver)
    assert running == (
        "Taking the first full backup (step 8 of 9), about 25 min so far; "
        "usually about 23 to 28 minutes."
    )
    assert done == "Operation succeeded, after about 25 min."
    assert bare == "Operation running, deploy."
    assert not any("%" in line or "90" in line for line in (running, done, bare))
    app = (PUBLIC / "app.js").read_text(encoding="utf-8")
    assert "status.textContent = describe(row, Date.now());" in app
    assert "stepStates(row, now)" in app and "typicalRange(row.expected)" in app
    assert "progress}%" not in app and "row.progress" not in app


def test_progress_is_dom_free_and_keeps_nothing() -> None:
    """It imports nothing, reads no DOM, no storage and no network, and keeps
    no state between calls: every function is a computation over its
    arguments (the module's only top-level bindings are constants and
    functions)."""
    text = PROGRESS.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
    assert not re.search(r"^\s*import\b", code, re.MULTILINE)
    for word in ("document", "window", "navigator", "localStorage", "sessionStorage",
                 "indexedDB", "fetch(", "WebSocket", "setTimeout", "setInterval"):  # fmt: skip
        assert word not in code, word
    top = re.findall(r"^(?:export )?(let|var|const|function|class)\b", code, re.MULTILINE)
    assert "let" not in top and "var" not in top and "class" not in top, top
