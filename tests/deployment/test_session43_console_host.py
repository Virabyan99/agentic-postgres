"""Session 43's host proofs: the console on the machine.

`CON-HOST-001` (claim `console_live_host`), run by the sweep as root after every
project moved to 1.21.0 (ADR 0280): the console's container runs on the control
project ONLY -- read from Docker's own labels across every container on the host,
not from a list of the projects this module knows -- healthy, at the limits the
release declares, read-only and unprivileged, on the edge network alone; and the
host still listens publicly on 22, 80, 443 and 5432 and nothing else. Reads
only. **None of these proofs has ever executed.**
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import config, naming
from agentic_postgres.listeners import parse_listeners, unexpected_public_ports

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST",
        "APG_PROJECT_A_OUTPUTS",
        "APG_PROJECT_B_OUTPUTS",
        "APG_CONTROL_OUTPUTS",
        "APG_LIVE_SLOT_OUTPUTS",
    ),
]

#: ADR 0268: the edge's three public ports and SSH; the console publishes none.
PUBLIC_PORTS = (22, 80, 443, 5432)
DOCUMENTS = ("APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS", "APG_CONTROL_OUTPUTS",
             "APG_LIVE_SLOT_OUTPUTS")  # fmt: skip


def _run(*command: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command), stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=timeout, check=False,
    )  # fmt: skip


def _inspect(name: str) -> dict[str, Any]:
    done = _run("docker", "inspect", name)
    assert done.returncode == 0, f"{name} does not exist"
    return json.loads(done.stdout)[0]


@pytest.fixture(scope="module")
def keys() -> dict[str, str]:
    """{gate variable: project key} from the four deployed documents."""
    found = {}
    for variable in DOCUMENTS:
        path = Path(os.environ.get(variable, ""))
        if not path.is_file():
            pytest.fail(f"{variable} points at {path}, which does not exist")
        found[variable] = json.loads(path.read_text(encoding="utf-8"))["project"]["key"]
    return found


def _console_container(key: str) -> str:
    return f"{naming.compose_project_name(key)}-{naming.CONSOLE_SERVICE}-1"


def test_the_console_runs_only_on_the_control_project(as_root: None, keys: dict[str, str]) -> None:
    """Every container on the host whose Compose service is `console` -- running
    or not -- is the control project's one; the control: that one is found by
    the same filter, so an empty answer cannot pass."""
    del as_root
    done = _run("docker", "ps", "-a", "--filter",
                f"label=com.docker.compose.service={naming.CONSOLE_SERVICE}",
                "--format", "{{.Names}}")  # fmt: skip
    assert done.returncode == 0, done.stderr.strip()[-300:]
    names = sorted(line for line in done.stdout.splitlines() if line.strip())
    assert names == [_console_container(keys["APG_CONTROL_OUTPUTS"])], names
    for variable, key in keys.items():
        if variable != "APG_CONTROL_OUTPUTS":
            assert _run("docker", "inspect", _console_container(key)).returncode != 0, key


def test_the_console_is_bounded(as_root: None, keys: dict[str, str]) -> None:
    """ADR 0280 / ADR 0244: running and healthy, with exactly the release's
    memory, process and CPU limits, read-only, every capability dropped, never
    root, no published port, on the edge network alone."""
    del as_root
    found = _inspect(_console_container(keys["APG_CONTROL_OUTPUTS"]))
    state = found["State"]
    assert state["Running"] is True and (state.get("Health") or {}).get("Status") == "healthy", (
        state["Status"], (state.get("Health") or {}).get("Status"),
    )  # fmt: skip
    limits = found["HostConfig"]
    assert limits["Memory"] == config.SERVICE_MEMORY_LIMITS_MB["console"] * 1024 * 1024
    defaults = config.SERVICE_RESOURCE_DEFAULTS["console"]
    assert limits["PidsLimit"] == defaults["pids_limit"], limits["PidsLimit"]
    assert limits["NanoCpus"] == int(float(defaults["cpus"]) * 1e9), limits["NanoCpus"]
    assert limits["ReadonlyRootfs"] is True and limits["CapDrop"] == ["ALL"], limits["CapDrop"]
    assert found["Config"]["User"] == "65532:65532", found["Config"]["User"]
    assert not any((found["NetworkSettings"]["Ports"] or {}).values()), found["NetworkSettings"]
    control = json.loads(
        Path(os.environ.get("APG_CONTROL_OUTPUTS", "")).read_text(encoding="utf-8")
    )
    networks = sorted(found["NetworkSettings"]["Networks"])
    assert networks == [control["edge"]["project_edge_network"]], networks


def test_the_listeners_did_not_change(as_root: None) -> None:
    """With the console running, the host listens publicly on 22, 80, 443 and
    5432 and nothing else. The control that the reading sees at all: the
    edge's 443 is in the same output."""
    del as_root
    done = _run("ss", "-H", "-lnt")
    assert done.returncode == 0, done.stderr
    seen = {item.port for item in parse_listeners(done.stdout) if not item.is_loopback}
    assert 443 in seen, "the edge is not listening on 443: the scan read an empty world"
    assert unexpected_public_ports(done.stdout, PUBLIC_PORTS) == (), sorted(seen)
