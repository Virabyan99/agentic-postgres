"""Shared plumbing for the host-local suite.

Everything here runs only on a provisioned deployment host, admitted by the
``requires_environment`` gate in ``tests/conftest.py``. Reading an environment
variable directly with ``os.environ[...]`` is deliberate: the gate has already
established the variable is set, so a ``KeyError`` here means the harness is
wrong, and that must surface as an error rather than as a skip.

Helpers are exposed as fixtures rather than as importable functions. ``tests/``
is not a package, so a test module cannot import its own conftest by name
without adding ``__init__.py`` files whose only purpose would be to make an
import work.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT

#: Signature of the plain-output command runner returned by the ``sh`` fixture.
Runner = Callable[..., str]

#: Signature of the exit-code-preserving runner returned by ``sh_status``.
StatusRunner = Callable[..., tuple[int, str, str]]


def _resolve(command: tuple[str, ...]) -> list[str]:
    first = command[0]
    executable = first if first.startswith("/") else shutil.which(first)
    if executable is None:
        pytest.fail(f"{first} is not installed on this host")
    return [executable, *command[1:]]


@pytest.fixture(scope="session")
def sh() -> Runner:
    """Run a host command and return stdout, failing the test on a bad exit.

    Failure is a test failure carrying stderr rather than a raised exception:
    on a live host the useful information is what the tool said, not where
    Python was standing when it said it.
    """

    def run(*command: str) -> str:
        result = subprocess.run(_resolve(command), capture_output=True, text=True, check=False)
        if result.returncode != 0:
            pytest.fail(
                f"`{' '.join(command)}` exited {result.returncode}\n"
                f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}"
            )
        return result.stdout

    return run


@pytest.fixture(scope="session")
def sh_status() -> StatusRunner:
    """Run a command and return ``(exit code, stdout, stderr)`` unjudged."""

    def run(*command: str) -> tuple[int, str, str]:
        result = subprocess.run(_resolve(command), capture_output=True, text=True, check=False)
        return result.returncode, result.stdout, result.stderr

    return run


@pytest.fixture(scope="session")
def as_root() -> None:
    """Fail rather than skip when root-only state is unreadable.

    A skip here would report "environment absent" for a run that *is* on the
    host and simply forgot ``sudo``, which is the one case where a quiet skip
    would hide a real gap in the evidence.
    """
    if os.geteuid() != 0:
        pytest.fail(
            "this test reads root-only host state; run it through "
            "`sudo bin/session-02-check.sh --mode host`"
        )


@pytest.fixture(scope="session")
def probe_image() -> str:
    """The digest-pinned image used for in-network probes.

    A floating tag here would make the probe's behaviour depend on whatever was
    published today, in a test whose whole purpose is to characterise a
    security boundary.
    """
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "PYTHON_RUNTIME_IMAGE":
            return value.strip()
    pytest.fail("PYTHON_RUNTIME_IMAGE is absent from versions.env")


def load_deployed(variable: str) -> dict[str, Any]:
    path = Path(os.environ[variable])
    if not path.is_file():
        pytest.fail(f"{variable} points at {path}, which does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def project_a() -> dict[str, Any]:
    return load_deployed("APG_PROJECT_A_OUTPUTS")


@pytest.fixture(scope="session")
def project_b() -> dict[str, Any]:
    return load_deployed("APG_PROJECT_B_OUTPUTS")


@pytest.fixture(scope="session")
def running_containers(sh: Runner) -> list[dict[str, Any]]:
    """Every running container, as parsed JSON rather than scraped columns."""
    raw = sh("docker", "ps", "--format", "{{json .}}")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]
