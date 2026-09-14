"""Transactional rendering (runbook §4.1, §9 checks 5-6, §15).

The property under test is the one that matters when something goes wrong: a
render that fails validation must leave the previous valid render exactly as
it was. Every test here renders once successfully, then breaks something, and
asserts the published bytes did not move.

These tests redirect the generated roots into ``tmp_path`` so they never touch
the repository's real ``.generated/``.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml
from checkout_owner import (
    as_checkout_owner,
    owned_by_the_checkout_owner,
    python_for_the_owner,
    traversable_to_the_checkout_owner,
)

from agentic_postgres import REPO_ROOT, config, rendering

#: The reading, made in a child so it can be made as somebody other than root.
#:
#: It imports through an explicit `sys.path` entry rather than relying on the
#: child inheriting pytest's `pythonpath` ini, which it does not.
_RESOLVE_AS_OWNER = """
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from agentic_postgres import rendering
print(json.dumps({
    "resolved": rendering.owner_of(pathlib.Path(sys.argv[2])),
    "me": rendering.current_user(),
}))
"""

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


# ---------------------------------------------------------------------------
# The render hands the checkout back, and says who has it (D1164, D1151)
# ---------------------------------------------------------------------------


def test_a_render_under_sudo_hands_the_directory_and_the_lock_back(
    sandbox: Path, manifest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D1164: every render hands back, not only the deploy's.

    `deploy-project.py` was repaired for D1110 and the RENDERER was not, so a
    root `--render-only` from anywhere else left `.generated/<key>` root-owned.
    `tests/deployment/test_session13_upgrade_plan.py`'s `candidate` fixture is
    exactly that -- it renders a real project's installed manifest, as root,
    during the live sweep, and removes what it published only if it created it
    -- and two op-side readers then crashed on what it left (D1151, D1154).

    `os.chown` is recorded rather than performed: the test runs unprivileged, so
    a real `chown` to another uid would raise, and what is under test is which
    paths the renderer decides to hand back.

    The control is in the same test (D499): with `SUDO_UID` unset, nothing is
    chowned at all. Without it, a function that chowned unconditionally would
    satisfy every assertion above it.
    """
    chowned: list[tuple[Path, int, int]] = []

    def record(path: object, uid: int, gid: int) -> None:
        chowned.append((Path(str(path)), uid, gid))

    monkeypatch.setattr(rendering.os, "chown", record)

    monkeypatch.setenv("SUDO_UID", "1234")
    monkeypatch.setenv("SUDO_GID", "5678")
    directory = rendering.render_project(manifest, CAPABILITIES)

    assert chowned, "a render under sudo handed nothing back"
    assert all(uid == 1234 and gid == 5678 for _, uid, gid in chowned), chowned

    handed = {path for path, _, _ in chowned}
    assert directory in handed, "the rendered directory itself was not handed back"
    assert any(path.name == "outputs.json" for path in handed), (
        "the directory was handed back and the documents inside it were not"
    )
    assert any(path.suffix == ".lock" for path in handed), (
        "the render lock was left root-owned, so the operator's NEXT render dies on "
        "the lock before it has validated anything (D65)"
    )

    # The control. A render with no sudo in front of it has nobody to hand
    # anything to, and must touch no ownership at all.
    chowned.clear()
    monkeypatch.delenv("SUDO_UID")
    monkeypatch.delenv("SUDO_GID")
    rendering.render_project(manifest, CAPABILITIES)
    assert chowned == [], f"an unprivileged render chowned {chowned}"


def test_publish_names_the_owner_and_the_remedy_when_it_cannot_replace(
    sandbox: Path, manifest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D1151: `[Errno 13] Permission denied` is not a report an operator can act on.

    The state is a `.generated/<key>` a privileged render left behind. What the
    operator needs is who owns it, who they are, and the command that hands it
    back -- ADR 0195's rule applied to the writer rather than the reader.

    The control, in the same test: an `OSError` that is NOT a permission problem
    keeps the old message, because "chown this" would be wrong advice for a full
    disk.
    """
    directory = rendering.render_project(manifest, CAPABILITIES)

    real_replace = os.replace
    calls = {"n": 0}

    def denied(src: object, dst: object) -> None:
        calls["n"] += 1
        if calls["n"] == 1:  # target -> backup, the first thing publish does
            raise PermissionError(13, "Permission denied")
        real_replace(src, dst)

    monkeypatch.setattr(rendering.os, "replace", denied)
    with pytest.raises(rendering.RenderError) as raised:
        rendering.render_project(manifest, CAPABILITIES)

    message = str(raised.value)
    assert "cannot replace" in message
    assert str(directory) in message
    assert "owned by" in message and "this user is" in message, message
    assert "chown" in message, "the remedy is not named, so the operator has only the problem"

    calls["n"] = 0

    def out_of_space(src: object, dst: object) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(28, "No space left on device")
        real_replace(src, dst)

    monkeypatch.setattr(rendering.os, "replace", out_of_space)
    with pytest.raises((rendering.RenderError, OSError)) as raised:
        rendering.render_project(manifest, CAPABILITIES)
    assert "chown" not in str(raised.value), (
        "a full disk was reported as an ownership problem, which sends the operator to "
        "the wrong remedy"
    )


def test_the_owner_is_resolved_upward_when_the_path_itself_cannot_answer(
    tmp_path: Path,
) -> None:
    """`owner_of` walks up rather than reporting nothing.

    A directory at mode 0000 refuses `stat` on everything inside it, so asking
    about the document gives `PermissionError` and asking about the directory
    gives the answer.

    **Under root this re-enters as the checkout's owner, and Session 25 is why**
    (D1302, D1310). Root stats through 0000, so as root there is nothing to walk
    up from -- and this carried a bare `pytest.skip` for that reason while the
    GATE runs its static claim proofs as root. It skipped on every run that
    could have recorded it, and `honest_readers` stayed `not_run` for three
    sessions with all 23 of its node ids written. D1165 repaired exactly this in
    `test_honest_readers.py`, and the repair never reached this module: the fix
    went to one caller of a decision rather than to the class, which is §7's
    fifth question.

    D1302 said it could not be shown offline. It can, and rig 25c did:
    `SKIPPED` as uid 0 in the pinned image, `PASSED` as a named non-root uid,
    and both arms re-run after this repair.
    """
    traversable_to_the_checkout_owner(tmp_path)

    directory = tmp_path / "shut"
    directory.mkdir()
    document = directory / "outputs.json"
    document.write_text("{}", encoding="utf-8")

    assert rendering.owner_of(document) == rendering.current_user()

    prefix = as_checkout_owner()
    if prefix:
        # The subject is WHOSE name comes back, so the fixture is handed to the
        # reader that will ask (D1332). Traversability alone left it owned by
        # root, and the child -- running as the owner -- correctly answered
        # `root`: a real failure, of a proof holding somebody else's fixture.
        # After the assertion above, which is the unprivileged reading.
        owned_by_the_checkout_owner(tmp_path, directory, document)
    resolved: str
    expected: str
    directory.chmod(0o000)
    try:
        if prefix:
            result = subprocess.run(
                [
                    *prefix,
                    python_for_the_owner(),
                    "-c",
                    _RESOLVE_AS_OWNER,
                    str(REPO_ROOT / "src"),
                    str(document),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            resolved = rendering.owner_of(document)
            expected = rendering.current_user()
    finally:
        directory.chmod(0o755)

    assert directory.stat().st_mode & 0o777 == 0o755, "the fixture directory was not restored"

    if prefix:
        assert result.returncode == 0, (
            f"the reading as the checkout owner did not run: {result.stderr.strip()[:400]}"
        )
        answer = json.loads(result.stdout)
        resolved, expected = answer["resolved"], answer["me"]

    assert resolved == expected, (
        f"the owner of an unreachable document resolved to {resolved!r}; the nearest "
        "ancestor that can answer is the point of walking upward"
    )
    assert rendering.owner_of(Path("/nonexistent/at/all")) in {"root", "unknown"}
