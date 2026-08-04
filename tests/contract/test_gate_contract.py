"""What ``bin/session-01-check.sh`` is allowed to assume (ADR 0014).

Two properties, both of which used to hold by accident and now hold by test.

**The gate does not know what session it is.** It asks the package. A literal
here made the registry policy and the tree's own ``CURRENT_SESSION`` disagree
the instant Session 2 activated its requirements, in a way no ordering of two
commits could keep green.

**The gate checks what it rendered, not what it found.** Globbing
``.generated/`` meant "no container is running for anything ever rendered on
this machine", which fails on a correct Session 2 deployment.

Neither is checked by reading the script's comments. Both are checked against
the bytes, and the session-derivation one is also checked by running it.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

import pytest

from agentic_postgres import CURRENT_SESSION, REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

GATE = REPO_ROOT / "bin" / "session-01-check.sh"


@pytest.fixture(scope="module")
def source() -> str:
    return GATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(source: str) -> str:
    """The script with comment lines removed.

    Every assertion below is about what the script *does*. Prose explaining why
    a session number is not hard-coded would otherwise fail the test that
    asserts no session number is hard-coded.
    """
    return "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))


# ---------------------------------------------------------------------------
# The acceptance session is derived
# ---------------------------------------------------------------------------


def test_the_gate_does_not_hard_code_a_session_number(code: str) -> None:
    offenders = [
        line.strip()
        for line in code.splitlines()
        if re.search(r"APG_ACCEPTANCE_SESSION\s*=\s*[\"']?\d", line)
    ]
    assert not offenders, f"the gate hard-codes an acceptance session: {offenders}"


def test_the_gate_derives_the_acceptance_session_from_the_package(code: str) -> None:
    assert "CURRENT_SESSION" in code, "the gate does not read CURRENT_SESSION"
    assert "export APG_ACCEPTANCE_SESSION" in code


def test_the_derivation_actually_produces_the_current_session() -> None:
    """Guard the guard: run the expression the gate runs.

    A test that only grepped for ``CURRENT_SESSION`` would pass on a broken
    command substitution that silently exported an empty string, which pytest
    would then treat as "no gate session at all".
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from agentic_postgres import CURRENT_SESSION; print(CURRENT_SESSION)",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(CURRENT_SESSION)
    assert result.stdout.strip().isdigit()


def test_the_gate_still_exports_the_variable_the_policy_reads(code: str) -> None:
    """``tests/conftest.py`` reads this exact name; a rename would silently
    fall back to the package default and stop testing the gate's intent."""
    assert re.search(r"^\s*export APG_ACCEPTANCE_SESSION\b", code, re.MULTILINE)


# ---------------------------------------------------------------------------
# Step 7 checks what step 3 published
# ---------------------------------------------------------------------------


def test_step_seven_iterates_what_step_three_recorded(code: str) -> None:
    assert 'for project_dir in "${RENDERED_DIRS[@]}"' in code, (
        "step 7 does not iterate the directories step 3 recorded"
    )


def test_no_step_globs_the_generated_root_for_projects(code: str) -> None:
    """The specific regression: ``for d in .generated/*/``."""
    offenders = [
        line.strip()
        for line in code.splitlines()
        if re.search(r"for\s+\w+\s+in\s+\S*\.generated/\*", line)
    ]
    assert not offenders, (
        f"the gate globs .generated/ for projects: {offenders}. "
        "That sweeps in deployed Session 2 projects, whose containers run by design."
    )


def test_the_gate_records_at_least_two_rendered_directories(code: str) -> None:
    """Narrowing the scope must not be able to empty it."""
    assert 'RENDERED_DIRS[@]}" -lt 2' in code or "RENDERED_DIRS[@]} -lt 2" in code, (
        "the gate no longer requires at least two rendered projects"
    )


def test_the_gate_names_no_fixture_identity(source: str) -> None:
    """§9: fixture identities live in manifests, never in deployable source.

    ``bin`` is inside ``test_repository_contract.SCAN_ROOTS`` so this is already
    covered, but the temptation when narrowing step 7 is precisely to write the
    two directory names here, so it is worth failing on directly.
    """
    for marker in ("fixture-alpha", "fixture-alpine", ".generated/fixture"):
        assert marker not in source, f"the gate hard-codes {marker!r}"


# ---------------------------------------------------------------------------
# The gate remains the only definition of passing
# ---------------------------------------------------------------------------


def test_ci_invokes_the_gate_rather_than_restating_it() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "bin/session-01-check.sh" in workflow, (
        "CI no longer runs the gate; a second definition of passing has appeared"
    )


def test_the_gate_is_executable_in_the_git_index() -> None:
    """The \\\\wsl$ trap: a mode lost in transit breaks CI, not the local run."""
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", "bin/session-01-check.sh"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.startswith("100755"), result.stdout.strip()


def test_the_gate_passes_shellcheck() -> None:
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck is not installed")
    result = subprocess.run(
        ["shellcheck", str(GATE)], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_gate_still_refuses_a_dirty_tree_for_evidence(code: str) -> None:
    """``--allow-dirty`` must remain unable to produce evidence."""
    assert "--allow-dirty" in code
    assert "write-session-evidence.py" in code
    allow_dirty_block = code.split("Session evidence")[-1]
    assert "ALLOW_DIRTY" in allow_dirty_block, (
        "the evidence step no longer checks whether the run was dirty"
    )


def test_every_referenced_path_exists(code: str) -> None:
    """A renamed script would otherwise fail only at gate time."""
    referenced = set(re.findall(r"\bbin/[a-z0-9-]+\.(?:sh|py)\b", code))
    missing = sorted(name for name in referenced if not (REPO_ROOT / name).exists())
    assert not missing, f"the gate invokes scripts that do not exist: {missing}"


def test_the_generated_directory_resolution_is_digest_based(code: str) -> None:
    """The resolution must not drift back to re-deriving a name.

    Re-deriving would duplicate ``naming.derive``'s rule in a shell script, and
    the copy would be the one nobody updates.
    """
    assert "project_sha256" in code, (
        "step 3 no longer identifies directories by the digest their outputs record"
    )


def test_helper_paths_are_relative_to_the_repository_root(code: str) -> None:
    """§8.5: the gate works when invoked from anywhere."""
    assert 'cd "$ROOT_DIR"' in code
    assert 'ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"' in code


def test_the_gate_reports_the_session_it_measured(source: str) -> None:
    """A gate whose session is derived must say which one it used.

    Otherwise the one thing a reader cannot recover from the output is the
    thing that changed.
    """
    assert "acceptance gate session" in (REPO_ROOT / "tests" / "conftest.py").read_text(
        encoding="utf-8"
    ), "pytest no longer reports the gate session in its header"
    del source
