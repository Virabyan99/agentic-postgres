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


#: The call that writes an evidence half. Both modes reach the writer through
#: it, so "before the evidence step" is one string rather than two.
EVIDENCE_CALL = "write_evidence"


def test_baseline_only_returns_before_the_evidence_step(source: str) -> None:
    """A host verdict from a run where every project test skipped is a lie."""
    body = source.split("mode_host()", 1)[1].split("\n}", 1)[0]
    assert "host baseline PASSED" in body, "the baseline-only branch is gone"
    assert body.index("host baseline PASSED") < body.index(EVIDENCE_CALL), (
        "--baseline-only reaches the evidence step"
    )
    early_return = body.index("host baseline PASSED")
    assert "return 0" in body[early_return : body.index(EVIDENCE_CALL)], (
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


# ---------------------------------------------------------------------------
# What each mode hands the evidence writer (ADR 0025)
# ---------------------------------------------------------------------------


def function_body(source: str, name: str) -> str:
    """One shell function's body, with quoting and line breaks normalised away.

    The assertions below are about which arguments reach a command, and in
    shell those are spread over continuations and wrapped in quotes that carry
    no meaning here.
    """
    body = source.split(f"{name}()", 1)[1].split("\n}", 1)[0]
    return " ".join(body.replace('"', "").replace("\\\n", " ").split())


@pytest.mark.parametrize("mode", ["host", "external"])
def test_each_mode_runs_its_static_claim_proofs(source: str, mode: str) -> None:
    """A claim's proofs are not all environment-gated.

    Each requirement also names contract tests that carry no marker, so the
    mode's own ``-m`` selector never collects them. A claim missing them comes
    out ``not_run``, and a half that reports ``not_run`` writes no evidence.
    """
    body = function_body(source, f"mode_{mode}")
    assert f"run_claim_proofs {mode}" in body, f"{mode} mode never runs the static claim proofs"


def test_the_writer_receives_both_artifacts_and_both_projects(source: str) -> None:
    """Claims are resolved from JUnit, so the writer has to be given the JUnit.

    Both files: the marker-selected suite, and the static proofs the marker
    cannot collect. And both projects — ``MUST_AGREE`` compares
    ``project_keys``, so a half naming one project of a two-project host would
    be refused as describing a different system, which is the merge working
    correctly on a lie.
    """
    body = function_body(source, EVIDENCE_CALL)
    assert "--junit ${suite_junit}" in body
    assert "--junit ${claims_junit}" in body
    assert "--project-b-outputs ${PROJECT_B_OUTPUTS}" in body


def test_the_claims_artifact_is_optional_and_stale_ones_are_removed(source: str) -> None:
    """A mode may carry no claim, and then no claims file is produced.

    Two failure modes sit here. Passing ``--junit`` for a file that does not
    exist makes the writer refuse; leaving a previous run's file in place makes
    it judge this run against that one. The writer is given the file only if it
    exists, and ``run_claim_proofs`` deletes it before deciding whether to write
    one.
    """
    assert "[ -f ${claims_junit} ] && arguments+=(--junit ${claims_junit})" in function_body(
        source, EVIDENCE_CALL
    )
    proofs = function_body(source, "run_claim_proofs")
    assert "rm -f ${junit}" in proofs
    assert proofs.index("rm -f ${junit}") < proofs.index("nodeids+=")


def test_a_failed_resolver_is_not_mistaken_for_an_empty_one(source: str) -> None:
    """Both produce no node IDs, and only one of them is a legitimate run.

    ``local listing="$(...)"`` returns the exit status of ``local``, so the
    status has to be read on its own line. That trap has already cost this
    repository one run: ``cmd; [ $? -eq 0 ]`` reported the exit code of ``[``.
    """
    proofs = function_body(source, "run_claim_proofs")
    assert "listing=$(claim_static_nodeids ${mode}) status=$?" in proofs, (
        "the resolver's exit status is not captured on its own line"
    )
    assert proofs.index("status=$?") < proofs.index("${#nodeids[@]} -eq 0")
    assert "die 6" in proofs


def test_no_claim_proofs_means_no_pytest_invocation(source: str) -> None:
    """``pytest`` with no node IDs collects the whole suite.

    The most expensive possible way to measure nothing, and it would write a
    JUnit file the writer would then judge claims against.
    """
    proofs = function_body(source, "run_claim_proofs")
    guard = proofs.index("${#nodeids[@]} -eq 0")
    assert guard < proofs.index("-m pytest"), "the empty case reaches pytest"
    assert "return 0" in proofs[guard : proofs.index("-m pytest")]


@pytest.mark.parametrize("mode", ["host", "external"])
def test_a_filtered_run_writes_no_evidence(source: str, mode: str) -> None:
    """-k selects a subset; a subset cannot support a claim about the whole.

    The same reasoning as --baseline-only, and the same shape: announce, and
    return before the writer rather than after it.
    """
    body = function_body(source, f"mode_{mode}")
    assert "evidence_is_supportable" in body, f"{mode} mode writes evidence from a -k run"
    guard = body.index("evidence_is_supportable")
    assert guard < body.index(EVIDENCE_CALL), (
        f"{mode} mode reaches the writer before checking whether -k was used"
    )
    assert "return 0" in body[guard : body.index(EVIDENCE_CALL)]


def test_the_filtered_run_guard_reads_the_keyword_variable(source: str) -> None:
    """Guard the guard: a predicate that is always true would disable nothing."""
    definition = source.split("evidence_is_supportable() {", 1)[1].split("}", 1)[0]
    assert "KEYWORD" in definition
