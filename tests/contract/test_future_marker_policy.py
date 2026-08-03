"""Future-marker lifecycle (runbook §4.6, §8.3, §12).

The two behaviours that matter cannot be tested in-process:

* An invalid marker raises ``pytest.UsageError`` from the collection hook,
  which aborts the entire run — including this test.
* Removing a marker must *activate* a failing placeholder, which means the
  test has to fail, which is not something an in-process assertion can observe.

Both therefore run pytest in a subprocess against a temporary file. That
subprocess harness is written once here and is the only thing in the suite
that deliberately expects a non-zero pytest exit.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

REGISTRY = REPO_ROOT / "tests" / "acceptance-registry.yaml"


@pytest.fixture(scope="module")
def registry() -> list[dict[str, Any]]:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def run_pytest_on(path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """Run pytest against a throwaway file outside the repository tree.

    ``PYTHONPATH`` is set explicitly because the target path lives in tmp_path,
    so pytest's rootdir is the temporary directory and the repository's
    ``pythonpath = src`` setting does not apply. Without it the copied conftest
    fails to import the package and every assertion below would be measuring an
    ImportError instead of the marker hook.
    """
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            str(path),
            *extra,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
    )


def write_test(directory: Path, body: str) -> Path:
    """Write a throwaway test *with a copy of the real conftest beside it*.

    Without this the subprocess runs against a file outside ``tests/``, pytest
    never loads ``tests/conftest.py``, and the marker hook under test does not
    execute — so every assertion below would pass or fail for the wrong reason.
    Copying the real conftest means these tests exercise the actual hook rather
    than a reimplementation of it.
    """
    import shutil

    shutil.copy(REPO_ROOT / "tests" / "conftest.py", directory / "conftest.py")
    path = directory / "test_generated_placeholder.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Marker metadata agrees with the registry, in both directions
# ---------------------------------------------------------------------------


def test_every_marker_requirement_exists_in_the_registry(
    future_markers: dict[str, tuple[int, str]], registry: list[dict[str, Any]]
) -> None:
    known = {entry["id"] for entry in registry}
    unknown = sorted(
        f"{node_id} -> {requirement}"
        for node_id, (_, requirement) in future_markers.items()
        if requirement not in known
    )
    assert not unknown, f"future markers naming unregistered requirements: {unknown}"


def test_every_marker_session_matches_the_registry(
    future_markers: dict[str, tuple[int, str]], registry: list[dict[str, Any]]
) -> None:
    sessions = {entry["id"]: entry["target_session"] for entry in registry}
    mismatched = sorted(
        f"{node_id}: marker says session {session}, registry says {sessions[requirement]}"
        for node_id, (session, requirement) in future_markers.items()
        if requirement in sessions and sessions[requirement] != session
    )
    assert not mismatched, f"marker/registry session disagreement: {mismatched}"


def test_every_later_requirement_has_a_placeholder(
    future_markers: dict[str, tuple[int, str]],
    registry: list[dict[str, Any]],
    gate_session: int,
) -> None:
    """A requirement owned by a later session must exist as an activatable test."""
    marked = {requirement for _, requirement in future_markers.values()}
    missing = sorted(
        entry["id"]
        for entry in registry
        if entry["target_session"] > gate_session and entry["id"] not in marked
    )
    assert not missing, f"later requirements with no future placeholder: {missing}"


def test_marker_node_ids_match_registered_node_ids(
    future_markers: dict[str, tuple[int, str]], registry: list[dict[str, Any]]
) -> None:
    registered = {node_id: entry["id"] for entry in registry for node_id in entry["test_nodeids"]}
    for node_id, (_, requirement) in future_markers.items():
        if node_id in registered:
            assert registered[node_id] == requirement, (
                f"{node_id} carries requirement {requirement} but is registered "
                f"under {registered[node_id]}"
            )


def test_no_requirement_is_claimed_by_two_placeholders(
    future_markers: dict[str, tuple[int, str]],
) -> None:
    requirements = [requirement for _, requirement in future_markers.values()]
    duplicates = sorted({r for r in requirements if requirements.count(r) > 1})
    assert not duplicates, f"a requirement has more than one placeholder: {duplicates}"


# ---------------------------------------------------------------------------
# The lifecycle itself
# ---------------------------------------------------------------------------


def test_marked_placeholder_is_collected_and_skipped(tmp_path: Path) -> None:
    path = write_test(
        tmp_path,
        """
        import pytest

        @pytest.mark.p0
        @pytest.mark.future(session=9, requirement="SEC-REV-001")
        def test_placeholder() -> None:
            pytest.fail("not implemented")
        """,
    )
    result = run_pytest_on(path)
    assert result.returncode == 0, result.stdout
    assert "1 skipped" in result.stdout


def test_removing_the_marker_activates_a_failing_placeholder(tmp_path: Path) -> None:
    """Runbook §12: this is what makes a placeholder genuinely activatable.

    A body calling ``pytest.skip()`` would stay green after the marker is
    removed, and the later session would inherit a test that proves nothing.
    """
    path = write_test(
        tmp_path,
        """
        import pytest

        @pytest.mark.p0
        def test_placeholder() -> None:
            pytest.fail("Replace this placeholder with the Session 9 implementation")
        """,
    )
    result = run_pytest_on(path)
    assert result.returncode != 0, "removing the marker did not activate the test"
    assert "1 failed" in result.stdout
    assert "Replace this placeholder" in result.stdout


def test_invalid_marker_aborts_collection(tmp_path: Path) -> None:
    path = write_test(
        tmp_path,
        """
        import pytest

        @pytest.mark.future(session="nine", requirement="SEC-REV-001")
        def test_placeholder() -> None:
            pytest.fail("not implemented")
        """,
    )
    result = run_pytest_on(path)
    assert result.returncode != 0
    assert "Invalid future marker" in result.stdout + result.stderr


def test_marker_without_a_requirement_aborts_collection(tmp_path: Path) -> None:
    path = write_test(
        tmp_path,
        """
        import pytest

        @pytest.mark.future(session=9)
        def test_placeholder() -> None:
            pytest.fail("not implemented")
        """,
    )
    result = run_pytest_on(path)
    assert result.returncode != 0
    assert "Invalid future marker" in result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Placeholder bodies must fail, not skip
# ---------------------------------------------------------------------------


def test_no_placeholder_body_calls_skip(future_markers: dict[str, tuple[int, str]]) -> None:
    """A placeholder that skips itself can never be activated."""
    import ast

    offenders: list[str] = []
    for node_id in future_markers:
        relative, _, name = node_id.partition("::")
        tree = ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                source = ast.dump(node)
                if "'skip'" in source:
                    offenders.append(node_id)
    assert not offenders, f"placeholders that skip instead of failing: {offenders}"


def test_all_future_tests_are_skipped_in_a_normal_run() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-m", "future"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "failed" not in result.stdout.splitlines()[-1]
    assert "skipped" in result.stdout


def test_markers_are_declared_in_pytest_ini() -> None:
    """`--strict-markers` means an undeclared marker is an error, not a typo."""
    text = (REPO_ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "--strict-markers" in text
    for marker in ("p0", "contract", "security", "integration", "recovery", "deployment"):
        assert f"\n    {marker}:" in text, f"marker {marker} is not declared"
    assert "future(session, requirement):" in text
