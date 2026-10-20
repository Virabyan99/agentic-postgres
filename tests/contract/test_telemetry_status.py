"""`telemetry.sh status` reads every container of the plane, the healthcheck-less one too (D2636).

The gateway is the projects' pinned contrib collector, and it has no
healthcheck. Session 42's Sheet T1 read it as `<id> (could not be read)`: the
whole `docker inspect` template failed with *map has no entry for key
"Health"*. Measured in Session 43's Run 2 (`~/s43/run2/d2636.txt`, Docker
29.5.2): the CLI executes an inspect template against its typed struct first
and falls back to the raw JSON map only when that fails. `.HostConfig.NanoCpus`
is not the struct's field name (`NanoCPUs`), so the status template always ran
against the map, where `{{if .State.Health}}` -- and `{{with .State.Health}}` --
fail on a missing key while `{{if index .State "Health"}}` reads it as absent.
The short template without `NanoCpus` worked, which is why the fault looked
intermittent from outside.

Docker-backed: two containers from the pinned collector image, one without a
healthcheck and one with (the control), read through the script's own
`do_status` with only `require_root` and `compose` replaced.
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.contract.test_image_contracts import LOCK, requires_docker

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, requires_docker]

SCRIPT = REPO_ROOT / "bin" / "telemetry.sh"
IMAGE = LOCK["OTEL_COLLECTOR_IMAGE"]


def _docker(*arguments: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, check=False, timeout=timeout
    )


@pytest.fixture(scope="module")
def containers() -> Iterator[dict[str, str]]:
    """`{"none": <id>, "checked": <id>}`, removed with their volumes afterwards."""
    suffix = uuid.uuid4().hex[:8]
    names = {"none": f"apg-s43-nohc-{suffix}", "checked": f"apg-s43-hc-{suffix}"}
    try:
        started = _docker("run", "-d", "--name", names["none"], IMAGE)
        assert started.returncode == 0, started.stderr
        started = _docker(
            "run", "-d", "--name", names["checked"],
            "--health-cmd", "true", "--health-interval", "2s", IMAGE,
        )  # fmt: skip
        assert started.returncode == 0, started.stderr
        yield {kind: _docker("inspect", "--format", "{{.Id}}", name).stdout.strip()
               for kind, name in names.items()}  # fmt: skip
    finally:
        _docker("rm", "-fv", *names.values(), timeout=120)


def _status(tmp_path: Path, ids: list[str]) -> subprocess.CompletedProcess[str]:
    """`do_status` from a copy of the script with `main` removed; `compose` names the ids."""
    text = SCRIPT.read_text(encoding="utf-8")
    # The copy sources `bin/lib/` beside the real script, so its root is the repository's.
    for old, new in (
        ('ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"',
         f'ROOT_DIR="{REPO_ROOT}"'),
        ('\nmain "$@"\n', "\n"),
    ):  # fmt: skip
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    copy = tmp_path / "telemetry.sh"
    copy.write_text(text, encoding="utf-8")
    listing = " ".join(ids)
    return subprocess.run(
        ["bash", "-c",
         f'. "{copy}"; require_root() {{ :; }}; '
         f"compose() {{ printf '%s\\n' {listing}; }}; do_status"],
        capture_output=True, text=True, check=False, timeout=60,
    )  # fmt: skip


def _line_for(output: str, name_prefix: str) -> str:
    lines = [line for line in output.splitlines() if line.startswith(f"/{name_prefix}")]
    assert len(lines) == 1, output
    return lines[0]


def test_a_container_without_a_healthcheck_is_read(
    tmp_path: Path, containers: dict[str, str]
) -> None:
    done = _status(tmp_path, [containers["none"], containers["checked"]])
    assert done.returncode == 0, done.stderr
    assert "(could not be read)" not in done.stdout, done.stdout
    line = _line_for(done.stdout, "apg-s43-nohc-")
    assert " running health=none " in line, line
    assert "mem_limit=" in line and "nanocpus=" in line, line


def test_a_container_with_one_is_read(tmp_path: Path, containers: dict[str, str]) -> None:
    """The control: the repair must still read a healthcheck that exists."""
    done = _status(tmp_path, [containers["checked"]])
    assert done.returncode == 0, done.stderr
    line = _line_for(done.stdout, "apg-s43-hc-")
    health = line.split(" health=", 1)[1].split(" ", 1)[0]
    assert health in {"starting", "healthy", "unhealthy"}, line
