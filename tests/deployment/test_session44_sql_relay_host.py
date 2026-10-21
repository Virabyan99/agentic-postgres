"""Session 44's host proofs: the SQL relay on the machine, and what it wrote.

`SQL-HOST-001` (claim `sql_relay_host`), run by the sweep as root after every
project moved to 1.22.0 and after the editor walk (ADR 0286): the relay's
container runs on the control project ONLY -- read from Docker's own labels
across every container on the host -- healthy, at the limits the release
declares, read-only and unprivileged, on the edge network alone, its peak
memory read from its own cgroup; the host still listens publicly on 22, 80,
443 and 5432 and nothing else; and **the relay's whole log holds the session
lines ADR 0286 allows and nothing else** -- no statement, no SASL word, no
marker (D2743), with the walk's own session to the live slot's pooled door
among them (the control that this is the log the walk wrote to). Reads only.
**None of these proofs has ever executed.**
"""

from __future__ import annotations

import json
import os
import re
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

#: ADR 0268: the edge's three public ports and SSH; the relay publishes none.
PUBLIC_PORTS = (22, 80, 443, 5432)
DOCUMENTS = ("APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS", "APG_CONTROL_OUTPUTS",
             "APG_LIVE_SLOT_OUTPUTS")  # fmt: skip

#: ADR 0286 decision 6: the only lines the relay writes.
SESSION_LINE = re.compile(
    r"apg-sql-relay session=[0-9a-f]{16} door=(?P<door>[a-z0-9.-]{1,253}) "
    r"outcome=(?P<outcome>closed|refused|unreachable) code=\d{1,4} seconds=\d+\.\d up=\d+ down=\d+"
)
REFUSED_LINE = re.compile(r"apg-sql-relay refused reason=(?:origin|path)")
#: What no line may hold: the walk's marker (any session's -- `apg-s44-<12 hex>`),
#: a statement, the SASL exchange.
FORBIDDEN = ("apg-s44-", "SELECT", "select ", "SCRAM", "n,,n=", "c=biws", "pg_sleep", "Traceback")


def _run(*command: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command), stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=timeout, check=False,
    )  # fmt: skip


def _inspect(name: str) -> dict[str, Any]:
    done = _run("docker", "inspect", name)
    assert done.returncode == 0, f"{name} does not exist"
    return json.loads(done.stdout)[0]


def _document(variable: str) -> dict[str, Any]:
    path = Path(os.environ.get(variable, ""))
    if not path.is_file():
        pytest.fail(f"{variable} points at {path}, which does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def keys() -> dict[str, str]:
    """{gate variable: project key} from the four deployed documents."""
    return {variable: _document(variable)["project"]["key"] for variable in DOCUMENTS}


def _relay_container(key: str) -> str:
    return f"{naming.compose_project_name(key)}-{naming.SQL_RELAY_SERVICE}-1"


def test_the_relay_runs_only_on_the_control_project(as_root: None, keys: dict[str, str]) -> None:
    """Every container on the host whose Compose service is `sql-relay` -- running
    or not -- is the control project's one; the control: that one is found by the
    same filter, so an empty answer cannot pass."""
    del as_root
    done = _run("docker", "ps", "-a", "--filter",
                f"label=com.docker.compose.service={naming.SQL_RELAY_SERVICE}",
                "--format", "{{.Names}}")  # fmt: skip
    assert done.returncode == 0, done.stderr.strip()[-300:]
    names = sorted(line for line in done.stdout.splitlines() if line.strip())
    assert names == [_relay_container(keys["APG_CONTROL_OUTPUTS"])], names
    for variable, key in keys.items():
        if variable != "APG_CONTROL_OUTPUTS":
            assert _run("docker", "inspect", _relay_container(key)).returncode != 0, key


def test_the_relay_is_bounded(as_root: None, keys: dict[str, str], record_property: Any) -> None:
    """ADR 0286 / ADR 0244: running and healthy, with exactly the release's
    memory, process and CPU limits, read-only, every capability dropped, never
    root, no published port, on the edge network alone -- and its cgroup's peak
    memory read and recorded (D2750), under its limit."""
    del as_root
    container = _relay_container(keys["APG_CONTROL_OUTPUTS"])
    found = _inspect(container)
    state = found["State"]
    assert state["Running"] is True and (state.get("Health") or {}).get("Status") == "healthy", (
        state["Status"], (state.get("Health") or {}).get("Status"),
    )  # fmt: skip
    limits = found["HostConfig"]
    assert limits["Memory"] == config.SERVICE_MEMORY_LIMITS_MB["sql-relay"] * 1024 * 1024
    defaults = config.SERVICE_RESOURCE_DEFAULTS["sql-relay"]
    assert limits["PidsLimit"] == defaults["pids_limit"], limits["PidsLimit"]
    assert limits["NanoCpus"] == int(float(defaults["cpus"]) * 1e9), limits["NanoCpus"]
    assert limits["ReadonlyRootfs"] is True and limits["CapDrop"] == ["ALL"], limits["CapDrop"]
    assert found["Config"]["User"] == "65532:65532", found["Config"]["User"]
    assert not any((found["NetworkSettings"]["Ports"] or {}).values()), found["NetworkSettings"]
    control = _document("APG_CONTROL_OUTPUTS")
    networks = sorted(found["NetworkSettings"]["Networks"])
    assert networks == [control["edge"]["project_edge_network"]], networks
    # No secret, no volume, no bind: no mount at all, and one tmpfs (compose's
    # `tmpfs: [/tmp]`, which Docker reports under HostConfig, not Mounts).
    assert (found.get("Mounts") or []) == [], found.get("Mounts")
    assert sorted(limits.get("Tmpfs") or {}) == ["/tmp"], limits.get("Tmpfs")  # noqa: S108
    peak = _run("docker", "exec", container, "cat", "/sys/fs/cgroup/memory.peak")
    assert peak.returncode == 0, peak.stderr.strip()[-200:]
    peak_mib = int(peak.stdout.strip()) / 1048576
    record_property("sql_relay_memory_peak_mib", f"{peak_mib:.1f}")
    print(f"sql-relay memory.peak {peak_mib:.1f} MiB")
    assert 0 < peak_mib < config.SERVICE_MEMORY_LIMITS_MB["sql-relay"]


def test_the_listeners_did_not_change(as_root: None) -> None:
    """With the relay running, the host listens publicly on 22, 80, 443 and
    5432 and nothing else. The control that the reading sees at all: the
    edge's 443 is in the same output."""
    del as_root
    done = _run("ss", "-H", "-lnt")
    assert done.returncode == 0, done.stderr
    seen = {item.port for item in parse_listeners(done.stdout) if not item.is_loopback}
    assert 443 in seen, "the edge is not listening on 443: the scan read an empty world"
    assert unexpected_public_ports(done.stdout, PUBLIC_PORTS) == (), sorted(seen)


def test_the_relay_logged_no_payload(as_root: None, keys: dict[str, str]) -> None:
    """D2743, live: the relay container's whole log, stdout and stderr, is
    session lines and refusal lines in ADR 0286's grammar and nothing else; no
    line holds a marker, a statement or a SASL word. The control: the editor
    walk's session to the live slot's pooled door is there, closed -- so this
    is the log the walk's statements passed through."""
    del as_root
    done = _run("docker", "logs", _relay_container(keys["APG_CONTROL_OUTPUTS"]), timeout=300)
    assert done.returncode == 0, done.stderr.strip()[-300:]
    lines = [line for line in (done.stdout + done.stderr).splitlines() if line.strip()]
    for word in FORBIDDEN:
        assert not any(word in line for line in lines), f"a relay line holds {word!r}"
    strays = [
        line[:80]
        for line in lines
        if not (SESSION_LINE.fullmatch(line) or REFUSED_LINE.fullmatch(line))
    ]
    assert strays == [], strays
    slot = _document("APG_LIVE_SLOT_OUTPUTS")
    pooled, _direct = naming.endpoint_hosts(slot["project"]["domain"])
    walked = [m for line in lines if (m := SESSION_LINE.fullmatch(line)) and m["door"] == pooled]
    assert any(m["outcome"] == "closed" for m in walked), (
        f"no closed session to {pooled}: the walk did not reach this relay, or this is not its log"
    )
