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


@pytest.fixture
def deploy_module():
    """The deploy, imported so a helper can be driven rather than grepped.

    Most of this module is a source-level contract because the deploy needs root
    and a host. `_restore_git_index_ownership` is the exception: it is pure
    filesystem work gated on `SUDO_UID`, so it can be *run*, and a text slice
    asserting the string ".git" appears would pass against a function that
    chowns nothing (D191).
    """
    import importlib.util

    path = REPO_ROOT / "bin" / "deploy-project.py"
    spec = importlib.util.spec_from_file_location("apg_deploy_project", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_git_index_is_handed_back_after_a_privileged_git_call(
    deploy_module, tmp_path, monkeypatch
) -> None:
    """D194: `git status` under sudo rewrites `.git/index` as `root:root` 0600.

    The operator's next `git fetch` then dies with "index file open failed:
    Permission denied", which reads as a broken repository rather than as a
    permission this deploy took. Transport to this host is a bundle and a fetch,
    so a deploy that breaks git breaks the only way to deliver the next one.

    `os.chown` is recorded rather than performed: the test runs unprivileged, so
    a real chown to the caller's own uid would succeed while proving nothing
    about *which* paths were reached.

    Goes red if the helper stops naming the index, or is called before the git
    commands that dirty it rather than after.
    """
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "index").write_bytes(b"")
    (git_dir / "ORIG_HEAD").write_bytes(b"")

    chowned: list[str] = []
    monkeypatch.setattr(deploy_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(deploy_module.os, "chown", lambda p, u, g: chowned.append(str(p)))
    monkeypatch.setenv("SUDO_UID", "1000")
    monkeypatch.setenv("SUDO_GID", "1000")

    deploy_module._restore_git_index_ownership()

    assert str(git_dir / "index") in chowned, f".git/index was not handed back; chowned {chowned}"
    # Only what exists: naming a file that is not there would be a chown on a
    # missing path, which fails per-target and hides the ones that matter.
    assert str(git_dir / "index.lock") not in chowned


def test_the_git_handback_does_nothing_outside_sudo(deploy_module, tmp_path, monkeypatch) -> None:
    """The control. Without SUDO_UID there is no operator to hand anything to.

    Goes red if the helper starts chowning during an unprivileged run, which
    would mean it is guessing at an owner rather than reading the one sudo
    recorded.
    """
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "index").write_bytes(b"")

    chowned: list[str] = []
    monkeypatch.setattr(deploy_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(deploy_module.os, "chown", lambda p, u, g: chowned.append(str(p)))
    monkeypatch.delenv("SUDO_UID", raising=False)
    monkeypatch.delenv("SUDO_GID", raising=False)

    deploy_module._restore_git_index_ownership()
    assert chowned == []


def test_the_router_name_is_read_back_not_re_derived(source: str, code_only) -> None:
    """Deriving the router name a second time creates a second path to the same
    answer; the deployed document would describe a project the render never
    produced."""
    body = code_only(source)
    assert "HEALTH_ROUTER_NAME" in body
    assert "health_router_name" not in body
