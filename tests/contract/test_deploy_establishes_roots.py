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


def test_the_render_lock_is_handed_back_with_the_rendered_directory(source: str) -> None:
    """D65: the lock lives outside the directory the deploy restores.

    `rendering.project_lock` opens `.generated/.locks/<key>.lock` at 0600, and
    under sudo that file belongs to root. Restoring only the rendered directory
    left it behind, so the next *unprivileged* render of that project died with
    `PermissionError` on the lock before it had validated anything. Latent since
    Session 2 and found on the host in Run 7, three sessions after the deploy
    that caused it.
    """
    body = source.split("def _restore_checkout_ownership")[1].split("\ndef ")[0]
    assert "LOCK_ROOT" in body, "the deploy restores the rendered directory but not the lock"


def test_the_router_name_is_read_back_not_re_derived(source: str, code_only) -> None:
    """Deriving the router name a second time creates a second path to the same
    answer; the deployed document would describe a project the render never
    produced."""
    body = code_only(source)
    assert "HEALTH_ROUTER_NAME" in body
    assert "health_router_name" not in body
