"""The Session 3 gate has two modes, and the third one's absence is a decision.

``bin/session-03-check.sh`` takes the shape ``bin/session-02-check.sh`` already
had — verify-only, ``--project-*-outputs`` naming *deployed* documents, ``-k``
writing no evidence (D45) — with two differences that are the whole content of
this module.

**There is no external mode.** Not "not yet": there is nothing new to see from
outside a cluster that publishes no host port and joins no edge network.
``SEC-NET-001``'s scan already covers 5432 and belongs to Session 2; Session 3 is
simply the first session in which that scan is not vacuous, because before it
nothing was listening. A mode that measured nothing would still write an evidence
file saying it had run, which is worse than not having it.

**``--project-b-outputs`` is required.** ``database_isolation`` is a claim about
two clusters. With one project every proof of it skips, the claim resolves to
``not_run``, and the run fails — after doing all the work. Refusing up front says
the same thing sooner, and says which argument.
"""

from __future__ import annotations

import subprocess

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCRIPT = REPO_ROOT / "bin" / "session-03-check.sh"
SESSION_TWO = REPO_ROOT / "bin" / "session-02-check.sh"
HOST_EXAMPLE = REPO_ROOT / "host.example.yaml"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args], capture_output=True, text=True, check=False, cwd=REPO_ROOT
    )


@pytest.fixture(scope="module")
def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_the_gate_exists_and_is_executable_in_the_git_index() -> None:
    """Asserted against the index: writing through the \\\\wsl$ share strips the
    bit, and a gate nobody can execute fails in a way that reads as a bad path."""
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", "bin/session-03-check.sh"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.startswith("100755 "), result.stdout.strip()


def test_help_exits_zero_and_names_both_modes() -> None:
    result = run("--help")
    assert result.returncode == 0
    assert "--mode offline" in result.stdout
    assert "--mode host" in result.stdout


def test_a_missing_mode_is_an_argument_error() -> None:
    result = run()
    assert result.returncode == 2
    assert "--mode is required" in result.stderr


# ---------------------------------------------------------------------------
# There is no external mode
# ---------------------------------------------------------------------------


def test_external_mode_is_refused_by_name_rather_than_as_a_typo() -> None:
    """An operator who ran the Session 2 gate's third mode is asking a reasonable
    question and deserves the answer, not "unknown mode"."""
    result = run("--mode", "external")
    assert result.returncode == 2
    assert "no external mode" in result.stderr


def test_the_external_arguments_are_refused_with_the_same_answer() -> None:
    result = run("--mode", "host", "--public-ipv4", "203.0.113.1")
    assert result.returncode == 2
    assert "no external mode" in result.stderr


def test_the_help_says_why_rather_than_omitting_it(source: str) -> None:
    """The absence is documented in the place an operator looks first.

    A mode that is simply missing from a usage block reads as an oversight, and
    the next person adds it back.
    """
    assert "There is no external mode" in run("--help").stdout
    assert "D45" in source


def test_the_script_never_writes_an_external_evidence_file(source: str) -> None:
    assert "session-03-external" not in source
    assert "--external-input" not in source


# ---------------------------------------------------------------------------
# Two projects, or nothing
# ---------------------------------------------------------------------------


def test_host_mode_without_project_b_is_an_argument_error(tmp_path) -> None:
    outputs = tmp_path / "outputs.json"
    outputs.write_text("{}", encoding="utf-8")
    result = run(
        "--mode", "host",
        "--host", str(HOST_EXAMPLE),
        "--project-a-outputs", str(outputs),
    )  # fmt: skip
    assert result.returncode == 2
    assert "--project-b-outputs" in result.stderr
    assert "two clusters" in result.stderr


def test_argument_errors_are_reported_without_needing_root(tmp_path) -> None:
    """Learning you mistyped a flag should not first require obtaining root.

    A valid command line refused for want of privilege is 3, a bad one is 2, and
    which you get does not depend on who you are.
    """
    outputs = tmp_path / "outputs.json"
    outputs.write_text("{}", encoding="utf-8")

    valid_but_unprivileged = run(
        "--mode", "host",
        "--host", str(HOST_EXAMPLE),
        "--project-a-outputs", str(outputs),
        "--project-b-outputs", str(outputs),
    )  # fmt: skip
    assert valid_but_unprivileged.returncode == 3
    assert "requires root" in valid_but_unprivileged.stderr

    invalid = run("--mode", "host", "--host", "/nonexistent.yaml")
    assert invalid.returncode == 2


def test_baseline_only_points_at_the_session_two_gate() -> None:
    """It exists there and means something there; here it would mean a run that
    measured no cluster, which is not a Session 3 verdict."""
    result = run("--mode", "host", "--baseline-only")
    assert result.returncode == 2
    assert "session-02-check.sh" in result.stderr


# ---------------------------------------------------------------------------
# It verifies, and it says which session it is answering for
# ---------------------------------------------------------------------------


def test_the_gate_deploys_nothing(source: str) -> None:
    """D20. A gate that deploys what it measures cannot be re-run to confirm a
    fix, and its result depends on whether it was the first run.

    Scanned over executable lines only. The usage text names ``./deploy.sh`` on
    purpose -- it is where an operator is sent when the gate reports a project
    is not deployed -- and step 1 passes ``deploy.sh`` to ``shellcheck``, which
    is reading it, not running it. A scan that could not tell those apart would
    have to be relaxed until it caught nothing.
    """
    for forbidden in ("./deploy.sh", "bin/project-runtime.sh", "bin/materialize-secrets"):
        assert forbidden not in _executable_lines(source), f"the gate invokes {forbidden}"


def test_the_gate_resolves_claims_for_its_own_session(source: str) -> None:
    """One CLAIMS table serves several gates, so each must name its session.

    Without it this gate would resolve every claim in the table, including ones
    a later session introduces, and report them as unproved (ADR 0039).
    """
    assert "readonly SESSION=3" in source
    assert "static_nodeids_for_mode(sys.argv[1], int(sys.argv[2]))" in source
    assert 'claim_static_nodeids "${mode}" "${SESSION}"' in source


def test_the_session_two_gate_still_names_session_two() -> None:
    """Guard the guard: the change that gave this gate a session had to give the
    other one one too, or Session 2's evidence would report Session 3's claims."""
    assert "static_nodeids_for_mode(sys.argv[1], 2)" in SESSION_TWO.read_text(encoding="utf-8")


def test_a_filtered_run_writes_no_evidence(source: str) -> None:
    body = source.split("mode_host()", 1)[1]
    assert "evidence_is_supportable" in body
    assert body.index("evidence_is_supportable") < body.index("write_evidence"), (
        "the -k guard runs after the evidence is written"
    )


def _executable_lines(text: str) -> str:
    """Source with comments and the usage heredoc removed.

    The heredoc is prose an operator reads; treating it as code makes every
    instruction the gate gives look like an action the gate takes.
    """
    kept: list[str] = []
    in_usage = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "cat <<'USAGE'":
            in_usage = True
            continue
        if stripped == "USAGE":
            in_usage = False
            continue
        if in_usage or stripped.startswith("#"):
            continue
        kept.append(line)
    return "\n".join(kept)


def test_the_usage_heredoc_is_actually_being_stripped(source: str) -> None:
    """Guard the guard: if the markers ever change, the scan above silently
    covers the whole file and starts failing on prose -- or, worse, the strip
    removes everything and the scan passes over nothing."""
    executable = _executable_lines(source)
    assert "There is no external mode. See the header" not in executable
    assert 'run_suite "live_host"' in executable
