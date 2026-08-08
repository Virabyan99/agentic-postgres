"""Every file the launcher and the runtime open is written by the deploy.

This is a source-level contract, not a behavioural one: `bin/deploy-project.py`
requires root and a provisioned host, so the test asserts that the code names
each destination and installs it atomically, and the host run proves the rest.
"""

from __future__ import annotations

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]


@pytest.fixture(scope="module")
def source() -> str:
    return (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "destination",
    ['"manifest.yaml"', '"secrets.required.yaml"', '"compose.env"'],
)
def test_the_deploy_writes_each_configuration_file(source: str, destination: str) -> None:
    assert destination in source, f"nothing in the deploy writes {destination}"


def test_the_rendered_directory_is_installed_out_of_the_checkout(source: str) -> None:
    """systemd may not run out of a working tree, and neither may the runtime
    read its Compose project directory from one."""
    assert "install_rendered" in source
    assert "rendered_path" in source


def test_the_install_is_atomic(source: str) -> None:
    """A half-written rendered directory is one the next boot treats as
    complete."""
    assert "os.replace" in source


def test_the_router_name_is_read_back_not_re_derived(source: str, code_only) -> None:
    """Deriving the router name a second time creates a second path to the same
    answer; the deployed document would describe a project the render never
    produced."""
    body = code_only(source)
    assert "HEALTH_ROUTER_NAME" in body
    assert "health_router_name" not in body
