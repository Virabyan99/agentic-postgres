"""What systemd runs is an installed release, not a checkout.

DEP-REL-001. The property is that ``git checkout`` on the operator's clone
cannot change what starts at the next boot. The offline half of that claim —
that no unit's ``Exec*`` line names a path into a checkout — is already asserted
by ``tests/contract/test_host_infrastructure.py``. This module measures the
other half on the host: the release exists, is root-owned, matches the commit it
claims, and is not the checkout.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

RELEASES_ROOT = Path("/opt/agentic-postgres/releases")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def output(*command: str) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return result.stdout


@pytest.fixture(scope="module")
def project_a() -> dict[str, Any]:
    return json.loads(Path(os.environ["APG_PROJECT_A_OUTPUTS"]).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def release(project_a: dict[str, Any]) -> Path:
    path = Path(project_a["runtime"]["release_path"])
    if not path.is_dir():
        pytest.fail(f"{path} is not installed")
    return path


# ---------------------------------------------------------------------------
# The release is what it claims to be
# ---------------------------------------------------------------------------


def test_the_release_directory_is_named_for_a_full_commit(release: Path) -> None:
    """A short hash or a branch name would make the path ambiguous over time."""
    assert release.parent == RELEASES_ROOT, release
    assert COMMIT.match(release.name), f"{release.name} is not a 40-character commit"


def test_the_release_is_root_owned_and_not_group_writable(release: Path) -> None:
    for path in [release, *release.rglob("*")]:
        stat = path.stat()
        assert stat.st_uid == 0, f"{path} is owned by uid {stat.st_uid}"
        assert not stat.st_mode & 0o022, (
            f"{path} is writable by group or other: {oct(stat.st_mode)}"
        )


def test_the_release_contains_no_symlink_escaping_itself(release: Path) -> None:
    offenders = [
        str(path)
        for path in release.rglob("*")
        if path.is_symlink() and not str(path.resolve()).startswith(str(release))
    ]
    assert not offenders, f"symlinks point outside the release: {offenders}"


def test_the_release_is_not_a_git_checkout(release: Path) -> None:
    """``git archive`` output has no ``.git``, so nothing there can be switched."""
    assert not (release / ".git").exists(), f"{release} carries a .git directory"


# ---------------------------------------------------------------------------
# Nothing executes from anywhere else
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unit",
    [
        "agentic-postgres-docker-firewall.service",
        "agentic-postgres-edge.service",
        "agentic-postgres-project@.service",
    ],
)
def test_the_installed_unit_executes_only_a_libexec_launcher(unit: str) -> None:
    """Read from systemd, not from ``systemd/`` in the repository.

    The repository copy is asserted offline. This asks what is installed, which
    is the only version that runs.
    """
    text = output("systemctl", "cat", unit)
    assert text.strip(), f"{unit} is not installed"

    execs = [
        line.split("=", 1)[1].strip()
        for line in text.splitlines()
        if re.match(r"\s*Exec(Start|StartPre|StartPost|Stop|StopPost|Reload)\s*=", line)
    ]
    assert execs, f"{unit} declares no Exec line"

    offenders = [
        command
        for command in execs
        if not command.lstrip("-+!@").startswith("/usr/local/libexec/agentic-postgres/")
    ]
    assert not offenders, f"{unit} executes something outside libexec: {offenders}"


def test_the_launchers_are_root_owned_and_not_writable_by_others() -> None:
    libexec = Path("/usr/local/libexec/agentic-postgres")
    assert libexec.is_dir(), f"{libexec} does not exist"

    launchers = sorted(libexec.iterdir())
    assert launchers, "no launcher is installed"
    for path in launchers:
        stat = path.stat()
        assert stat.st_uid == 0, f"{path} is owned by uid {stat.st_uid}"
        assert not stat.st_mode & 0o022, f"{path} is writable by group or other"
        assert stat.st_mode & 0o100, f"{path} is not executable"


def test_the_installed_launchers_are_the_ones_this_release_ships() -> None:
    """The check that was missing, and the one D72 needed.

    Every assertion above characterises the *release*, and every one of them
    passed on a host whose launchers were two sessions old. Nothing compared the
    file systemd actually executes against the file the repository ships,
    because until Run 8 nothing but provisioning ever installed one -- so the
    two were expected to drift and the drift had no name.

    Byte comparison against the checkout, not against a project's recorded
    release: with ADR 0037 a launcher resolves a release and holds nothing a
    release owns, so all of them should be identical anyway, and the checkout is
    the one copy that is under review. A checkout moved to a commit nobody
    deployed fails this, and that failure says the right thing -- the host is
    running a launcher that is not the one in this tree.
    """
    repository = Path(__file__).resolve().parents[2] / "libexec"
    libexec = Path("/usr/local/libexec/agentic-postgres")

    shipped = sorted(repository.glob("agentic-postgres-*"))
    assert shipped, "the repository ships no launchers"

    stale = []
    for origin in shipped:
        installed = libexec / origin.name.removeprefix("agentic-postgres-")
        if not installed.is_file():
            stale.append(f"{installed} is not installed")
        elif installed.read_bytes() != origin.read_bytes():
            stale.append(f"{installed} differs from {origin}")

    assert not stale, (
        "the host executes launchers other than the ones this release ships: "
        + "; ".join(stale)
        + ". Deploy a project to reinstall them."
    )


def test_the_running_containers_come_from_an_installed_release(
    project_a: dict[str, Any], release: Path
) -> None:
    """Compose records its project directory; it must be an installed release.

    The property being defended is that nothing runs out of a working tree: a
    `git checkout` must not be able to change what a running deployment is made
    of. Any directory under the immutable release root satisfies that.

    It deliberately does not demand the *recorded* release. `compose up -d`
    does not recreate a container whose configuration has not changed, which is
    what makes a no-op redeploy free of downtime -- so after installing a new
    release the containers legitimately still carry the previous release's
    working directory until something about them actually changes. Requiring an
    exact match failed on every second deploy while the security property held
    perfectly.
    """
    key = project_a["project"]["key"]
    working_dirs = {
        line.strip()
        for line in output(
            "docker",
            "ps",
            "--filter",
            f"label=apg.project.key={key}",
            "--format",
            '{{.Label "com.docker.compose.project.working_dir"}}',
        ).splitlines()
        if line.strip()
    }
    assert working_dirs, f"no running container records a Compose working directory for {key}"

    state = Path(project_a["runtime"]["state_directory"])
    release_root = release.parent
    offenders = sorted(
        path
        for path in working_dirs
        if path != str(state) and release_root not in Path(path).parents
    )
    assert not offenders, (
        f"containers were started from outside the release root {release_root} "
        f"and outside the state directory: {offenders}"
    )

    # An installed release that no longer exists on disk is not immutability, it
    # is a dangling reference: the code those containers were made from can no
    # longer be inspected or reproduced.
    missing = sorted(path for path in working_dirs if not Path(path).is_dir())
    assert not missing, f"containers name release directories that no longer exist: {missing}"
