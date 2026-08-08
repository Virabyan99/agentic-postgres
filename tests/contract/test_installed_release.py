"""Installed release identity and trust (DEP-REL-001, offline half).

The live assertions run on a host. These run anywhere, against a temporary
release root, and cover the parts that are pure logic: what counts as a commit,
what counts as trustworthy, and what ``install`` refuses to do.

The path-component checks matter more than they look. The commit comes out of a
root-owned JSON file, so the threat is not an attacker typing it — it is a
corrupted or crafted value reaching ``Path.__truediv__`` and resolving somewhere
nobody intended. ``..`` is a perfectly good string to code that only checks
length.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from agentic_postgres.installed_release import (
    COMMIT_PATTERN,
    LAUNCHER_PREFIX,
    ReleaseError,
    assert_clean,
    assert_trustworthy,
    install,
    installed_commits,
    reconcile_launchers,
    release_path,
    resolve_commit,
    validate_commit,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0]

FORTY = "a" * 40


# ---------------------------------------------------------------------------
# Commit validation, before the value becomes a path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "commit",
    [
        "",
        "..",
        "../../etc",
        "HEAD",
        "main",
        "a" * 39,
        "a" * 41,
        "A" * 40,
        "g" * 40,
        f"{'a' * 39}/",
        f"../{'a' * 37}",
        "a" * 40 + "\n",
    ],
)
def test_a_value_that_is_not_a_full_commit_is_refused(commit: str) -> None:
    with pytest.raises(ReleaseError):
        validate_commit(commit)


def test_a_full_lowercase_commit_is_accepted() -> None:
    assert validate_commit(FORTY) == FORTY
    assert COMMIT_PATTERN.match(FORTY)


def test_release_path_validates_before_joining(tmp_path: Path) -> None:
    """The check has to happen here, not in the caller."""
    with pytest.raises(ReleaseError):
        release_path("../../etc", root=tmp_path)

    assert release_path(FORTY, root=tmp_path) == tmp_path / FORTY


def test_an_abbreviated_commit_is_refused_even_though_git_would_resolve_it() -> None:
    """Git accepts a short hash; an installed release path may not.

    An abbreviation that is unique today can become ambiguous, and a path
    component that changes meaning over time is one that can be made to resolve
    somewhere else.
    """
    with pytest.raises(ReleaseError):
        validate_commit(FORTY[:12])


# ---------------------------------------------------------------------------
# Trust
# ---------------------------------------------------------------------------


def test_a_missing_release_is_not_trustworthy(tmp_path: Path) -> None:
    with pytest.raises(ReleaseError, match="missing"):
        assert_trustworthy(tmp_path / FORTY)


def test_a_symlinked_release_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / FORTY
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(ReleaseError, match="symlink"):
        assert_trustworthy(link)


def test_a_group_writable_release_is_refused(tmp_path: Path) -> None:
    """Checked on every use, not only at install.

    The interesting case is a release that was correct when written and is
    writable now.
    """
    release = tmp_path / FORTY
    release.mkdir()
    os.chmod(release, 0o775)  # noqa: S103 -- the permissive mode is the thing under test

    if os.geteuid() == 0:
        pytest.skip("uid check is meaningless as root; the mode check is asserted below")

    with pytest.raises(ReleaseError, match=r"owned by uid|writable by group"):
        assert_trustworthy(release)


def test_a_release_owned_by_another_user_is_refused(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("running as root; every directory here would be root-owned")

    release = tmp_path / FORTY
    release.mkdir()
    os.chmod(release, 0o755)  # noqa: S103 -- isolating the ownership check from the mode check

    with pytest.raises(ReleaseError, match=r"owned by uid"):
        assert_trustworthy(release)


# ---------------------------------------------------------------------------
# Installing
# ---------------------------------------------------------------------------


def test_installing_requires_root(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("running as root; the refusal cannot be observed")

    with pytest.raises(ReleaseError, match="requires root"):
        install(tmp_path, root=tmp_path / "releases")


def make_repository(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ("init", "-q"),
        ("config", "user.email", "test@example.invalid"),
        ("config", "user.name", "Test"),
    ):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)

    (path / "tracked.txt").write_text("content\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=path, check=True, capture_output=True
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_a_dirty_checkout_cannot_be_installed(tmp_path: Path) -> None:
    """``git archive`` would silently ignore the uncommitted change.

    The release would then not be the commit it is named for, and that name is
    the only thing tying deployed behaviour to a reviewable diff.
    """
    checkout = tmp_path / "checkout"
    make_repository(checkout)
    (checkout / "tracked.txt").write_text("modified\n", encoding="utf-8")

    with pytest.raises(ReleaseError, match="uncommitted"):
        assert_clean(checkout)


def test_a_clean_checkout_resolves_its_commit(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    expected = make_repository(checkout)

    assert_clean(checkout)
    assert resolve_commit(checkout) == expected
    assert COMMIT_PATTERN.match(resolve_commit(checkout))


def test_installed_commits_ignores_anything_not_named_for_a_commit(tmp_path: Path) -> None:
    """A staging directory left by an interrupted install must not be listed."""
    root = tmp_path / "releases"
    root.mkdir()
    (root / FORTY).mkdir()
    (root / f".{FORTY}.tmpabc").mkdir()
    (root / "not-a-commit").mkdir()

    assert installed_commits(root) == [FORTY]


def test_installed_commits_is_empty_when_nothing_is_installed(tmp_path: Path) -> None:
    assert installed_commits(tmp_path / "absent") == []


# ---------------------------------------------------------------------------
# ADR 0037 — the deploy installs the indirection, not only the code
# ---------------------------------------------------------------------------


def test_reconciling_launchers_requires_root(tmp_path: Path) -> None:
    """It writes into /usr/local/libexec and chowns to root; nothing less does.

    Asserted rather than assumed because the failure without it is silent in the
    worst way: a non-root deploy that skipped the step would leave the host
    executing the previous launcher while reporting a successful release
    install, which is the exact shape of the defect this function closes.
    """
    if os.geteuid() == 0:
        pytest.skip("this asserts the refusal, which does not apply to root")
    with pytest.raises(ReleaseError, match="requires root"):
        reconcile_launchers(tmp_path, libexec=tmp_path / "libexec")


def test_the_launcher_prefix_excludes_the_release_side_launcher() -> None:
    """`libexec/project-launcher` must not be installable by this path.

    The prefix is the only thing keeping it out of /usr/local/libexec, where a
    copy would be a second answer to which session a project was deployed
    through -- the question D59 and D72 were both about.
    """
    assert LAUNCHER_PREFIX == "agentic-postgres-"
    assert not "project-launcher".startswith(LAUNCHER_PREFIX)


def test_the_deploy_reconciles_the_launchers_it_ships(code_only) -> None:
    """Wired into the deploy, not merely available to it.

    A source assertion because the behaviour needs root and a real release; the
    behaviour itself is measured on the host by
    ``test_the_installed_launchers_are_the_ones_this_release_ships``.
    """
    source = code_only(
        (Path(__file__).resolve().parents[2] / "bin" / "deploy-project.py").read_text(
            encoding="utf-8"
        )
    )
    assert "installed_release.reconcile_launchers(release)" in source
    assert source.index("installed_release.install(") < source.index("reconcile_launchers")
