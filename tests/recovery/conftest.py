"""Fixtures for the recovery proofs.

`tests/deployment/conftest.py` holds the loaders these need and does not reach
here — pytest does not chain conftests across sibling directories. They are
**imported** rather than re-written: a second `load_deployed` is a second reading
of `APG_PROJECT_B_OUTPUTS`, and the two would agree until one of them learned
something (D264).
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

import pytest
from tests.deployment.conftest import load_deployed


@pytest.fixture(scope="session")
def project_b() -> dict[str, Any]:
    """Beta's deployed document.

    Beta, not alpha, and the plan says why: the drill runs in the frozen example
    domain under a drill-only owner id, and beta is the project this session may
    disturb.
    """
    return load_deployed("APG_PROJECT_B_OUTPUTS")


@pytest.fixture(scope="session")
def require_root() -> None:
    """The drill creates a volume and two containers over the local socket."""
    if os.geteuid() != 0:
        pytest.fail(
            "the restore drill reads root-owned state and reaches the Docker daemon; "
            "run it through `sudo bin/session-10-check.sh --mode host`"
        )


def psql(document: dict[str, Any], statement: str, *, user: str = "postgres") -> str:
    """One statement against the live cluster, over its own socket.

    ``-i`` is not optional even with nothing on stdin: `docker exec` without it
    discards input silently and exits 0, so a block that ran nothing looks
    exactly like one that worked (D552).
    """
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            document["database"]["container"],
            "psql",
            "-U",
            user,
            "-d",
            document["database"]["name"],
            "-X",
            "-qtA",
            "-c",
            statement,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, f"{statement}\n{result.stderr.strip()}"
    return result.stdout.strip()
