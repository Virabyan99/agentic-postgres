"""`bin/project-runtime.sh stop|start`: sleep and wake (LIFE-SLEEP-001; D2155, ADR 0259).

The script is run for real, as a subprocess, from a copy in a throwaway root
whose `bin/` holds RECORDERS in place of the commands it calls -- `compose.sh`,
`edge-network.sh`, `materialize-secrets.sh` and the two renderers -- each of
which appends its argv to a log and exits as the test says. The copy's two
host roots are pointed under tmp by replacing their literals, each replacement
count-asserted; `id` is a recorder too, answering root.

What is proved is the order and the absences: `stop` detaches the edge FIRST
and then runs `compose stop` -- never `down`, never `rm`; `start` runs `compose
start --wait` and attaches only once it returned 0, and materializes nothing,
renders nothing, builds nothing.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

KEY = "slot1-prod"
STATE_LITERAL = 'readonly PROJECT_STATE_ROOT="/etc/agentic-postgres/projects"'
RENDERED_LITERAL = 'readonly PROJECT_RENDERED_ROOT="/var/lib/agentic-postgres/rendered"'

#: Each stand-in appends "<name> <argv...>" to $RECORD_LOG; `compose.sh` fails
#: with $COMPOSE_EXIT when its argv contains $COMPOSE_FAIL_ON.
RECORDER = """#!/usr/bin/env bash
printf '%s %s\\n' "$(basename "$0")" "$*" >> "${RECORD_LOG}"
if [ "$(basename "$0")" = compose.sh ] && [ -n "${COMPOSE_FAIL_ON:-}" ]; then
  case " $* " in *" ${COMPOSE_FAIL_ON} "*) exit "${COMPOSE_EXIT:-1}" ;; esac
fi
exit 0
"""
ID = """#!/usr/bin/env bash
if [ "$1" = "-u" ]; then printf '%s\\n' "${FAKE_UID:-0}"; else exec /usr/bin/id "$@"; fi
"""


def _executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def root(tmp_path: Path) -> dict[str, Path]:
    tree = tmp_path / "release"
    (tree / "bin").mkdir(parents=True)
    state = tmp_path / "etc-projects"
    rendered = tmp_path / "var-rendered"
    (state / KEY).mkdir(parents=True)
    (rendered / KEY).mkdir(parents=True)
    source = (REPO_ROOT / "bin" / "project-runtime.sh").read_text(encoding="utf-8")
    for literal, replacement in (
        (STATE_LITERAL, f'readonly PROJECT_STATE_ROOT="{state}"'),
        (RENDERED_LITERAL, f'readonly PROJECT_RENDERED_ROOT="{rendered}"'),
    ):
        assert source.count(literal) == 1, literal
        source = source.replace(literal, replacement)
    _executable(tree / "bin" / "project-runtime.sh", source)
    for name in (
        "compose.sh",
        "edge-network.sh",
        "materialize-secrets.sh",
        "render-secret-override.py",
        "render-mount-digests.py",
    ):
        _executable(tree / "bin" / name, RECORDER)
    fake = tmp_path / "fake-bin"
    fake.mkdir()
    _executable(fake / "id", ID)
    # A python3 that is the recorder too, so a renderer reached through
    # `python_bin` is logged under its script's name rather than run.
    _executable(
        fake / "python3",
        '#!/usr/bin/env bash\nexec bash "$1" "${@:2}"\n',
    )
    host = tmp_path / "host.yaml"
    host.write_text("schema_version: 4\n", encoding="utf-8")
    return {
        "script": tree / "bin" / "project-runtime.sh",
        "fake": fake,
        "log": tmp_path / "record.log",
        "host": host,
        "rendered": rendered / KEY,
    }


def run(root: dict[str, Path], *arguments: str, **env: str) -> tuple[int, list[str], str]:
    root["log"].write_text("", encoding="utf-8")
    done = subprocess.run(
        [str(root["script"]), *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        stdin=subprocess.DEVNULL,
        env={
            **os.environ,
            "PATH": f"{root['fake']}:{os.environ['PATH']}",
            "RECORD_LOG": str(root["log"]),
            **env,
        },
    )
    log = [line for line in root["log"].read_text(encoding="utf-8").splitlines() if line]
    return done.returncode, log, done.stderr


def _action(root: dict[str, Path], action: str, **env: str) -> tuple[int, list[str], str]:
    return run(
        root, "--host", str(root["host"]), "--project-key", KEY, "--through-session", "38",
        action, **env,
    )  # fmt: skip


def test_stop_detaches_first_then_stops_and_keeps_the_containers(root: dict[str, Path]) -> None:
    code, log, err = _action(root, "stop")
    assert code == 0, err
    assert len(log) == 2, log
    assert log[0] == f"edge-network.sh detach --project-key {KEY}"
    compose = log[1].split()
    assert compose[:3] == ["compose.sh", str(root["rendered"]), "--runtime"]
    assert compose[-1] == "stop"
    assert compose.count("--profile") == 37 and "session38" in compose
    for word in ("down", "rm", "kill", "-v", "--volumes"):
        assert word not in compose, word


def test_start_waits_then_attaches_and_materializes_nothing(root: dict[str, Path]) -> None:
    code, log, err = _action(root, "start")
    assert code == 0, err
    assert len(log) == 2, log
    compose = log[0].split()
    assert compose[:3] == ["compose.sh", str(root["rendered"]), "--runtime"]
    assert compose[-4:] == ["start", "--wait", "--wait-timeout", "120"]
    assert log[1] == f"edge-network.sh attach --project-key {KEY}"
    joined = "\n".join(log)
    for absent in (
        "materialize-secrets",
        "render-secret-override",
        "render-mount-digests",
        "--build",
        " up ",
    ):
        assert absent not in joined, absent


def test_a_start_that_never_becomes_healthy_attaches_nothing(root: dict[str, Path]) -> None:
    """Exit 9, and no route pointed at containers that did not come up."""
    code, log, err = _action(root, "start", COMPOSE_FAIL_ON="start", COMPOSE_EXIT="1")
    assert code == 9, err
    assert "did not become healthy" in err
    assert not any(line.startswith("edge-network.sh") for line in log), log
    # Control: a stop is unaffected by the same failure setting.
    assert _action(root, "stop", COMPOSE_FAIL_ON="start")[0] == 0


def test_stop_and_start_need_root_and_the_session(root: dict[str, Path]) -> None:
    for action in ("stop", "start"):
        code, log, err = _action(root, action, FAKE_UID="1000")
        assert (code, log) == (3, []), (action, err)
        assert "requires root" in err
        missing = run(root, "--host", str(root["host"]), "--project-key", KEY, action)
        assert missing[0] == 2 and "--through-session" in missing[2], action
        deferred = run(
            root, "--host", str(root["host"]), "--project-key", KEY, "--through-session", "38",
            "--defer", "postgrest", action,
        )  # fmt: skip
        assert deferred[0] == 2 and "--defer applies to up" in deferred[2], action
