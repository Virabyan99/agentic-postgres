"""Transactional rendering (runbook §4.1, §9 checks 5-6, §15).

The property under test is the one that matters when something goes wrong: a
render that fails validation must leave the previous valid render exactly as
it was. Every test here renders once successfully, then breaks something, and
asserts the published bytes did not move.

These tests redirect the generated roots into ``tmp_path`` so they never touch
the repository's real ``.generated/``.
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

import pytest
import yaml

from agentic_postgres import REPO_ROOT, config, rendering

pytestmark = [pytest.mark.contract, pytest.mark.p0]

GENERATED_FILES = ("outputs.json", "compose.env", "rendered-summary.txt")
CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every generated root into an isolated directory."""
    generated = tmp_path / ".generated"
    generated.mkdir()
    monkeypatch.setattr(rendering, "GENERATED_ROOT", generated)
    monkeypatch.setattr(rendering, "STAGING_ROOT", generated / ".staging")
    monkeypatch.setattr(rendering, "LOCK_ROOT", generated / ".locks")
    return generated


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    """A private, editable copy of the alpha fixture."""
    path = tmp_path / "project.yaml"
    shutil.copy(REPO_ROOT / "project.example.yaml", path)
    return path


def snapshot(directory: Path) -> dict[str, bytes]:
    return {name: (directory / name).read_bytes() for name in GENERATED_FILES}


def corrupt(manifest: Path, **changes: object) -> None:
    document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    for dotted, value in changes.items():
        section, _, field = dotted.partition("__")
        document[section][field] = value
    manifest.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# The happy path, so the failure cases have something to preserve
# ---------------------------------------------------------------------------


def test_render_publishes_all_three_files(sandbox: Path, manifest: Path) -> None:
    directory = rendering.render_project(manifest, CAPABILITIES)
    assert directory == sandbox / "fixture-alpha-dev"
    for name in GENERATED_FILES:
        assert (directory / name).is_file()


def test_staging_is_empty_after_a_successful_render(sandbox: Path, manifest: Path) -> None:
    rendering.render_project(manifest, CAPABILITIES)
    assert list((sandbox / ".staging").iterdir()) == []


# ---------------------------------------------------------------------------
# A failed render preserves the last valid output
# ---------------------------------------------------------------------------


def test_failed_render_preserves_the_previous_output(sandbox: Path, manifest: Path) -> None:
    directory = rendering.render_project(manifest, CAPABILITIES)
    before = snapshot(directory)

    corrupt(manifest, database__pool_size=99999)
    with pytest.raises(config.ManifestError):
        rendering.render_project(manifest, CAPABILITIES)

    assert snapshot(directory) == before


def test_failed_render_leaves_no_staging_residue(sandbox: Path, manifest: Path) -> None:
    rendering.render_project(manifest, CAPABILITIES)

    corrupt(manifest, project__slug="INVALID")
    with pytest.raises(config.ManifestError):
        rendering.render_project(manifest, CAPABILITIES)

    assert list((sandbox / ".staging").iterdir()) == []


def test_failed_first_render_publishes_nothing(sandbox: Path, manifest: Path) -> None:
    corrupt(manifest, project__domain="not a domain")
    with pytest.raises(config.ManifestError):
        rendering.render_project(manifest, CAPABILITIES)

    assert not (sandbox / "fixture-alpha-dev").exists()


def test_schema_failure_on_staged_output_preserves_the_previous_render(
    sandbox: Path, manifest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail *after* staging, which is the window rollback exists for."""
    directory = rendering.render_project(manifest, CAPABILITIES)
    before = snapshot(directory)

    def reject(document: object, schema_name: str) -> None:
        if schema_name == "outputs.schema.json":
            raise config.ManifestError("injected staged-output failure")

    monkeypatch.setattr(config, "validate_against_schema", reject)

    with pytest.raises(config.ManifestError, match="injected"):
        rendering.render_project(manifest, CAPABILITIES)

    assert snapshot(directory) == before
    assert list((sandbox / ".staging").iterdir()) == []


def test_publish_failure_rolls_the_previous_directory_back(
    sandbox: Path, manifest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second rename fails; the first must be undone."""
    directory = rendering.render_project(manifest, CAPABILITIES)
    before = snapshot(directory)

    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src: object, dst: object) -> None:
        calls["n"] += 1
        if calls["n"] == 2:  # staging -> target
            raise OSError("injected publish failure")
        real_replace(src, dst)

    monkeypatch.setattr(rendering.os, "replace", flaky)

    with pytest.raises(rendering.RenderError, match="failed to publish"):
        rendering.render_project(manifest, CAPABILITIES)

    assert directory.is_dir(), "the previous render was not rolled back"
    assert snapshot(directory) == before


# ---------------------------------------------------------------------------
# Symlink refusal (runbook §4.1 step 3, §9 check 6)
# ---------------------------------------------------------------------------


def test_symlinked_target_directory_is_refused(sandbox: Path, manifest: Path) -> None:
    elsewhere = sandbox.parent / "elsewhere"
    elsewhere.mkdir()
    (sandbox / "fixture-alpha-dev").symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(rendering.RenderError, match="symlink"):
        rendering.render_project(manifest, CAPABILITIES)

    assert list(elsewhere.iterdir()) == [], "a render escaped through the symlink"


def test_symlinked_generated_root_is_refused(
    tmp_path: Path, manifest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real-generated"
    real.mkdir()
    link = tmp_path / "linked-generated"
    link.symlink_to(real, target_is_directory=True)

    monkeypatch.setattr(rendering, "GENERATED_ROOT", link)
    monkeypatch.setattr(rendering, "STAGING_ROOT", link / ".staging")
    monkeypatch.setattr(rendering, "LOCK_ROOT", link / ".locks")

    with pytest.raises(rendering.RenderError, match="symlink"):
        rendering.render_project(manifest, CAPABILITIES)


def test_symlinked_manifest_is_refused(tmp_path: Path, sandbox: Path) -> None:
    link = tmp_path / "linked-project.yaml"
    link.symlink_to(REPO_ROOT / "project.example.yaml")
    with pytest.raises(config.ManifestError, match="symlink"):
        rendering.render_project(link, CAPABILITIES)


def test_refuse_symlink_accepts_a_regular_path(tmp_path: Path) -> None:
    regular = tmp_path / "regular"
    regular.mkdir()
    rendering.refuse_symlink(regular)


# ---------------------------------------------------------------------------
# Per-project lock (plan decision I)
# ---------------------------------------------------------------------------


def test_concurrent_render_is_refused(sandbox: Path, manifest: Path) -> None:
    with (
        rendering.project_lock("fixture-alpha-dev"),
        pytest.raises(rendering.RenderError, match="another render holds the lock"),
    ):
        rendering.render_project(manifest, CAPABILITIES)


def test_lock_is_released_after_a_successful_render(sandbox: Path, manifest: Path) -> None:
    rendering.render_project(manifest, CAPABILITIES)
    with rendering.project_lock("fixture-alpha-dev"):
        pass  # acquiring again must not raise


def test_lock_is_released_after_a_failed_render(sandbox: Path, manifest: Path) -> None:
    corrupt(manifest, project__slug="INVALID")
    with pytest.raises(config.ManifestError):
        rendering.render_project(manifest, CAPABILITIES)
    with rendering.project_lock("fixture-alpha-dev"):
        pass


def test_different_projects_do_not_block_each_other(sandbox: Path) -> None:
    with rendering.project_lock("fixture-alpha-dev"), rendering.project_lock("fixture-alpine-dev"):
        pass


def test_lock_file_is_owner_only(sandbox: Path) -> None:
    with rendering.project_lock("fixture-alpha-dev"):
        path = sandbox / ".locks" / "fixture-alpha-dev.lock"
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


# ---------------------------------------------------------------------------
# Staged files are private before they are published
# ---------------------------------------------------------------------------


def test_write_private_sets_owner_only_mode_regardless_of_umask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = os.umask(0o000)
    try:
        path = tmp_path / "private.txt"
        rendering.write_private(path, b"data\n")
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    finally:
        os.umask(previous)


def test_write_private_refuses_to_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "once.txt"
    rendering.write_private(path, b"first\n")
    with pytest.raises(FileExistsError):
        rendering.write_private(path, b"second\n")
