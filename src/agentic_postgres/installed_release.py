"""Immutable installed releases under ``/opt/agentic-postgres/releases/{commit}``.

What systemd runs must not be a checkout. The launchers under ``libexec/``
already enforce that at boot; this module is the other half — the code that
*creates* a release, and the shared rules both halves agree on.

Three rules, each of which exists because of a specific way this goes wrong:

**A release is named by a full 40-character commit.** Validated before the value
is ever used as a path component. The state files that record it are root-owned,
but a corrupted or crafted value must still not be able to point a root unit at
an arbitrary directory, and ``..`` is a perfectly good hexadecimal-looking
string to someone not checking.

**A release is what ``git archive`` produced, not what the tree contains.**
Archiving from a commit rather than copying a working directory means untracked
files, editor state, and a dirty index cannot reach the host.

**A release is root-owned and not writable by anyone else.** Otherwise changing
what a root unit executes requires no privilege at all.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

#: Where installed releases live. Absolute and outside any checkout.
RELEASE_ROOT = Path("/opt/agentic-postgres/releases")

#: A full commit. Abbreviations are refused: they are ambiguous over time, and
#: an ambiguous path component is one that can be made to resolve elsewhere.
#:
#: ``\Z`` rather than ``$``, and ``fullmatch`` rather than ``match``. In Python
#: ``$`` also matches immediately before a trailing newline, so ``^[0-9a-f]{40}$``
#: accepts a 41-character string ending in ``\n`` -- which is exactly what a
#: commit read from a file with a stray newline looks like.
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")

#: Modes that must not be set on anything inside a release.
GROUP_OTHER_WRITE = stat.S_IWGRP | stat.S_IWOTH


class ReleaseError(RuntimeError):
    """A release could not be installed, or is not trustworthy."""


def validate_commit(commit: str) -> str:
    """Return ``commit`` if it is a full hexadecimal commit, else raise.

    Called before the value becomes a path component, never after.
    """
    if not COMMIT_PATTERN.fullmatch(commit):
        raise ReleaseError(
            f"not a full 40-character commit: {commit!r}. "
            "An abbreviated or non-hexadecimal value is refused because it is "
            "about to be used as a path component."
        )
    return commit


def release_path(commit: str, *, root: Path = RELEASE_ROOT) -> Path:
    """The directory a given commit installs to."""
    return root / validate_commit(commit)


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def resolve_commit(checkout: Path, revision: str = "HEAD") -> str:
    """Resolve a revision in ``checkout`` to a full commit."""
    return validate_commit(git("rev-parse", revision, cwd=checkout))


def assert_clean(checkout: Path) -> None:
    """Refuse to install from a dirty tree.

    ``git archive`` would silently ignore the uncommitted changes, so the
    release would not be the commit it claims to be — and that claim is the
    only thing tying deployed behaviour back to a reviewable diff.
    """
    if git("status", "--porcelain", cwd=checkout):
        raise ReleaseError(
            "the checkout has uncommitted changes; a release must be exactly "
            "the commit it is named for"
        )


def assert_trustworthy(path: Path) -> None:
    """Refuse a release root or ancestor that is not root-owned and tight.

    Checked on every use, not only at install time. A release that was correct
    when written and is group-writable now is the interesting case.
    """
    if not path.is_dir():
        raise ReleaseError(f"installed release is missing: {path}")
    if path.is_symlink():
        raise ReleaseError(f"installed release path is a symlink: {path}")

    info = path.stat()
    if info.st_uid != 0:
        raise ReleaseError(f"installed release is owned by uid {info.st_uid}, expected root")
    if info.st_mode & GROUP_OTHER_WRITE:
        raise ReleaseError(f"installed release is writable by group or other: {oct(info.st_mode)}")


def install(checkout: Path, *, commit: str | None = None, root: Path = RELEASE_ROOT) -> Path:
    """Install a release from ``checkout`` and return its path.

    Idempotent: installing a commit that is already present verifies it and
    returns, rather than rewriting it. Rewriting would mean a redeploy could
    change the bytes behind a commit that other state already points at.

    The archive is extracted into a sibling temporary directory and renamed into
    place, so an interrupted install leaves no half-populated release for a
    launcher to find and run.
    """
    if os.geteuid() != 0:
        raise ReleaseError("installing a release requires root")

    assert_clean(checkout)
    resolved = validate_commit(commit) if commit else resolve_commit(checkout)
    target = release_path(resolved, root=root)

    if target.exists():
        assert_trustworthy(target)
        return target

    # S103: 0o755 is world-*traversable*, not world-writable. Unprivileged
    # services under the release run as non-root and must be able to reach their
    # own files; the write bits are what matter and harden() strips them.
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o755)  # noqa: S103

    staging = Path(tempfile.mkdtemp(prefix=f".{resolved}.", dir=root))
    try:
        os.chmod(staging, 0o755)  # noqa: S103
        archive = staging / "release.tar"
        with archive.open("wb") as handle:
            result = subprocess.run(  # noqa: S603
                ["git", "archive", "--format=tar", resolved],  # noqa: S607
                cwd=checkout,
                stdout=handle,
                stderr=subprocess.PIPE,
                check=False,
            )
        if result.returncode != 0:
            raise ReleaseError(f"git archive failed: {result.stderr.decode(errors='replace')}")

        content = staging / "content"
        content.mkdir()
        extract = subprocess.run(  # noqa: S603
            ["tar", "--extract", "--file", str(archive), "--directory", str(content)],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        if extract.returncode != 0:
            raise ReleaseError(f"tar extract failed: {extract.stderr.strip()}")

        archive.unlink()
        harden(content)
        content.rename(target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    assert_trustworthy(target)
    return target


def harden(path: Path) -> None:
    """Make everything root-owned and unwritable by group and other.

    ``git archive`` preserves only the executable bit, so ownership comes from
    the installing process. Doing this before the rename means a launcher can
    never observe a release that is briefly permissive.
    """
    for current in [path, *path.rglob("*")]:
        if current.is_symlink():
            raise ReleaseError(f"release archive contains a symlink: {current}")
        os.chown(current, 0, 0)
        mode = current.stat().st_mode
        os.chmod(current, mode & ~GROUP_OTHER_WRITE)


def installed_commits(root: Path = RELEASE_ROOT) -> list[str]:
    """Every installed release, newest-first by modification time."""
    if not root.is_dir():
        return []
    releases = [p for p in root.iterdir() if p.is_dir() and COMMIT_PATTERN.fullmatch(p.name)]
    return [p.name for p in sorted(releases, key=lambda p: p.stat().st_mtime, reverse=True)]
