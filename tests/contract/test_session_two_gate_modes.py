"""Host mode has to be runnable one run before anything is deployed.

The host is provisioned in Run 5 and the first project is deployed in Run 6, so
there is a window in which the baseline is worth verifying and no project
outputs exist. ``--mode host`` required ``--project-a-outputs`` and so could not
be run at all in that window.

The plan's own Run 5 checklist reached for ``--tests-only``, a flag D20 had
already decided against — verify-only is the default, and deployment is an
explicit action. The checklist was never updated to match the decision above it,
which is how an instruction nobody could follow survived into a live run.

``--baseline-only`` is an explicit flag rather than an inference from a missing
argument. An argument whose *absence* silently changes what a command means is
one typo away from an evidence run that measured nothing and said it passed.
"""

from __future__ import annotations

import subprocess

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCRIPT = REPO_ROOT / "bin" / "session-02-check.sh"
HOST_EXAMPLE = REPO_ROOT / "host.example.yaml"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args], capture_output=True, text=True, check=False, cwd=REPO_ROOT
    )


@pytest.fixture(scope="module")
def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_baseline_only_is_documented(source: str) -> None:
    result = run("--help")
    assert result.returncode == 0
    assert "--baseline-only" in result.stdout


def test_host_mode_without_projects_is_an_argument_error_not_a_crash() -> None:
    """Exit 2 names the missing argument and offers --baseline-only."""
    result = run("--mode", "host", "--host", str(HOST_EXAMPLE))
    assert result.returncode == 2
    assert "--baseline-only" in result.stderr


def test_baseline_only_and_project_outputs_contradict(tmp_path) -> None:
    outputs = tmp_path / "outputs.json"
    outputs.write_text("{}", encoding="utf-8")
    result = run(
        "--mode",
        "host",
        "--host",
        str(HOST_EXAMPLE),
        "--baseline-only",
        "--project-a-outputs",
        str(outputs),
    )
    assert result.returncode == 2
    assert "contradict" in result.stderr


def test_argument_errors_are_reported_without_needing_root() -> None:
    """Learning you mistyped a flag should not first require obtaining root.

    Established in bin/provision-host.sh and applied here for consistency: a
    valid command line refused for want of privilege is 3, a bad one is 2, and
    which you get does not depend on who you are.
    """
    valid_but_unprivileged = run("--mode", "host", "--host", str(HOST_EXAMPLE), "--baseline-only")
    assert valid_but_unprivileged.returncode == 3
    assert "requires root" in valid_but_unprivileged.stderr

    invalid = run("--mode", "host", "--host", "/nonexistent.yaml", "--baseline-only")
    assert invalid.returncode == 2


def test_baseline_only_returns_before_the_evidence_step(source: str) -> None:
    """A host verdict from a run where every project test skipped is a lie."""
    body = source.split("mode_host()", 1)[1].split("\n}", 1)[0]
    assert "host baseline PASSED" in body, "the baseline-only branch is gone"
    assert body.index("host baseline PASSED") < body.index("write-session-evidence.py"), (
        "--baseline-only reaches the evidence step"
    )
    early_return = body.index("host baseline PASSED")
    assert "return 0" in body[early_return : body.index("write-session-evidence.py")], (
        "the baseline-only branch announces a result and then carries on regardless"
    )


def test_baseline_only_does_not_export_the_project_gate(source: str) -> None:
    """The gate variable must stay unset, so project tests skip rather than run.

    ``requires_environment("APG_PROJECT_A_OUTPUTS")`` is what makes the skip
    happen. Exporting the variable unconditionally would point every project
    test at an empty value instead, and they would fail rather than skip.
    """
    body = source.split("mode_host()", 1)[1].split("\n}", 1)[0]
    export_line = next(line for line in body.splitlines() if "APG_PROJECT_A_OUTPUTS=" in line)
    before_export = body[: body.index(export_line)]
    guards = [line for line in before_export.splitlines() if "BASELINE_ONLY" in line]
    assert any("-eq 0" in line for line in guards), (
        "APG_PROJECT_A_OUTPUTS is exported without checking --baseline-only"
    )
