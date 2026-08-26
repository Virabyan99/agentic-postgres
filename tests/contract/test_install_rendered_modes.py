"""The installer preserves the render's modes; it does not re-decide them (D589).

`install_rendered` copied the rendered directory into `/var/lib/agentic-postgres/
rendered/<key>/` and then **re-imposed `0600` on everything** except the
migration set. That made it a second authority over a decision `rendering.py`
had already taken three times -- `FILE_MODE`, `MIGRATION_FILE_MODE`,
`SNAPSHOT_MODE` -- and the installer won.

The visible consequence was D588's repair not working. The archiver's config was
rendered `0444` for a container running as 999 and **installed `0600`**, so
pgBackRest refused it with `[041]: unable to open file ... Permission denied` --
at the deploy's step 6c, and at every `archive_command` after it. Two deploys
were spent on it: the first fixed the render, and the second failed identically
because the render was never what the container read.

The latent half is worth stating too: the OpenAPI snapshots are rendered `0444`
for the same reason, and were being installed `0600` as well. Nothing reported
it, because the docs container's healthcheck does not read its snapshot.

**`os.chown` is patched out and the mode is not.** Ownership needs root and is
not the property under test; making the test require root would put it in the
one place it is least likely to run.
"""

from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]


@pytest.fixture(scope="module")
def deploy_project():
    """`bin/deploy-project.py`, imported by path because of the hyphen."""
    spec = importlib.util.spec_from_file_location(
        "apg_deploy_project", REPO_ROOT / "bin" / "deploy-project.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _rendered_fixture(tmp_path: Path) -> Path:
    """A source tree shaped like a render, with the three modes that matter."""
    source = tmp_path / "rendered"
    (source / "migrations").mkdir(parents=True)

    # 0600: describes a deployment, read by root.
    (source / "compose.env").write_text("COMPOSE_PROJECT_NAME=apg-x\n", encoding="utf-8")
    (source / "outputs.json").write_text("{}", encoding="utf-8")
    # 0444: read by a container that is not the owner.
    (source / "pgbackrest.conf").write_text("[global]\n", encoding="utf-8")
    (source / "openapi.json").write_text("{}", encoding="utf-8")
    # 0644 inside a 0755 directory: the migration set.
    (source / "migrations" / "0001.sql").write_text("SELECT 1;\n", encoding="utf-8")

    for name, mode in (
        ("compose.env", 0o600),
        ("outputs.json", 0o600),
        ("pgbackrest.conf", 0o444),
        ("openapi.json", 0o444),
    ):
        os.chmod(source / name, mode)
    # S103 is suppressed: 0755 on a migrations directory is exactly what
    # MIGRATION_DIRECTORY_MODE renders, and reproducing it is the point.
    os.chmod(source / "migrations", 0o755)  # noqa: S103
    os.chmod(source / "migrations" / "0001.sql", 0o644)
    os.chmod(source, 0o700)
    return source


def test_every_rendered_mode_survives_installation(
    deploy_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The property, stated over the whole tree rather than per file.

    Naming the files would leave the next artefact uncovered, which is exactly
    how the archiver's config was missed: the installer had an exemption list of
    one and the render had grown a third category.
    """
    monkeypatch.setattr(deploy_project.os, "chown", lambda *a, **k: None)

    source = _rendered_fixture(tmp_path)
    before = {
        path.relative_to(source).as_posix(): stat.S_IMODE(path.stat().st_mode)
        for path in source.rglob("*")
    }

    destination = deploy_project.install_rendered(source, tmp_path / "installed", b"services: {}\n")

    for relative, mode in before.items():
        installed = destination / relative
        assert installed.exists(), f"{relative} was not installed"
        assert stat.S_IMODE(installed.stat().st_mode) == mode, (
            f"{relative} was rendered {oct(mode)} and installed "
            f"{oct(stat.S_IMODE(installed.stat().st_mode))}. The installer is "
            "re-deciding a mode the render already decided (D589)."
        )


def test_the_container_readable_files_are_still_readable_after_installation(
    deploy_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The consequence, asserted directly and not only as equality.

    Equality alone would pass if the render itself regressed to 0600, so this
    names the two artefacts a non-owning container reads and requires the
    other-read bit on both -- with `outputs.json` as the control that must NOT
    have it.
    """
    monkeypatch.setattr(deploy_project.os, "chown", lambda *a, **k: None)

    destination = deploy_project.install_rendered(
        _rendered_fixture(tmp_path), tmp_path / "installed", b"services: {}\n"
    )

    for name in ("pgbackrest.conf", "openapi.json"):
        mode = (destination / name).stat().st_mode
        assert mode & stat.S_IROTH, (
            f"{name} is {oct(stat.S_IMODE(mode))} after installation; the container "
            "that reads it is neither its owner nor in its group"
        )

    control = (destination / "outputs.json").stat().st_mode
    assert not control & stat.S_IROTH, (
        "outputs.json is world-readable after installation; it describes a "
        "deployment and nothing mounts it into a container"
    )


def test_the_runtime_override_is_written_root_only(
    deploy_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one file the installer does write, and it must stay private.

    It carries values from root-owned host state. Removing the blanket chmod
    must not have widened it by omission.
    """
    monkeypatch.setattr(deploy_project.os, "chown", lambda *a, **k: None)

    destination = deploy_project.install_rendered(
        _rendered_fixture(tmp_path), tmp_path / "installed", b"services: {}\n"
    )
    override = destination / "runtime-compose.override.yaml"
    assert override.is_file()
    assert not override.stat().st_mode & (stat.S_IROTH | stat.S_IRGRP), (
        f"the runtime override is {oct(stat.S_IMODE(override.stat().st_mode))}"
    )
