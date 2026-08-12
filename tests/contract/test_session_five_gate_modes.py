"""The Session 5 gate has three modes, and the third one's return is a decision.

``bin/session-05-check.sh`` takes the shape the Session 2, 3 and 4 gates
already had — verify-only, ``--project-*-outputs`` naming *deployed* documents,
``-k`` writing no evidence (D45) — with the differences that are the content of
this module.

**External mode returns, and it is not vacuous.** Session 3 dropped it because
nothing new was visible from outside a cluster that published no port. Session 4
restores it (D82) for a reason that then changed under measurement: the plan
restored it because Session 4 publishes host ports, and ADR 0044 established
that nothing is published at all. The mode survives that intact, because what it
proves was never "the publication is bound to loopback" — it is that no database
transport is reachable from off-host, and it is where ``bin/connect.sh`` and the
broker can be exercised as what they are, a developer's programs reaching the
host over SSH.

**Both halves are required.** ``transport_boundary`` and ``connection_tooling``
are measured from off-host (ADR 0045), so a Session 4 document cannot be written
from a host run alone. The gate says so on the way out of each mode rather than
leaving the operator to discover it from the writer.

**Two flags admit proofs that would otherwise skip**, and a skip is not a pass:
``--rotated-from-file`` for the credential that a rotation replaced, and
``--after-reboot`` for the claim that the clusters came back by themselves.
"""

from __future__ import annotations

import subprocess

import pytest

from agentic_postgres import REPO_ROOT
from agentic_postgres import evidence_claims as claims

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCRIPT = REPO_ROOT / "bin" / "session-05-check.sh"
SESSION_PREVIOUS = REPO_ROOT / "bin" / "session-04-check.sh"
HOST_EXAMPLE = REPO_ROOT / "host.example.yaml"

SESSION = 5


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args], capture_output=True, text=True, check=False, cwd=REPO_ROOT
    )


@pytest.fixture(scope="module")
def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


@pytest.fixture
def outputs(tmp_path):
    path = tmp_path / "outputs.json"
    path.write_text("{}", encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_the_gate_exists_and_is_executable_in_the_git_index() -> None:
    """Asserted against the index: writing through the \\\\wsl$ share strips the
    bit, and a gate nobody can execute fails in a way that reads as a bad path."""
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", "bin/session-05-check.sh"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.startswith("100755 "), result.stdout.strip()


def test_help_exits_zero_and_names_all_three_modes() -> None:
    result = run("--help")
    assert result.returncode == 0
    for mode in ("--mode offline", "--mode host", "--mode external"):
        assert mode in result.stdout, mode


def test_a_missing_mode_is_an_argument_error() -> None:
    result = run()
    assert result.returncode == 2
    assert "--mode is required" in result.stderr


def test_an_unknown_mode_names_the_three_that_exist() -> None:
    result = run("--mode", "hostile")
    assert result.returncode == 2
    assert "offline, host or external" in result.stderr


# ---------------------------------------------------------------------------
# The runbook's flags, answered rather than rejected as typos (D82)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flag", "answer"),
    [("--capabilities", "deployed documents"), ("--external-probe", "--public-ipv4")],
)
def test_the_runbook_flags_are_answered_by_name(flag: str, answer: str) -> None:
    """An operator reading the runbook is asking a reasonable question.

    The runbook's shape for this gate was
    ``--capabilities … --external-probe <target>``. Neither exists; both have a
    real counterpart. "unknown argument" would send that operator looking for a
    typo instead of at the answer.
    """
    result = run(flag, "value")
    assert result.returncode == 2
    assert answer in result.stderr


def test_baseline_only_points_at_the_session_two_gate() -> None:
    result = run("--mode", "host", "--baseline-only")
    assert result.returncode == 2
    assert "session-02-check.sh" in result.stderr


# ---------------------------------------------------------------------------
# Host mode: two projects, or nothing
# ---------------------------------------------------------------------------


def test_host_mode_without_project_b_is_an_argument_error(outputs: str) -> None:
    result = run(
        "--mode", "host",
        "--host", str(HOST_EXAMPLE),
        "--project-a-outputs", outputs,
    )  # fmt: skip
    assert result.returncode == 2
    assert "--project-b-outputs" in result.stderr
    assert "two projects" in result.stderr


def test_argument_errors_are_reported_without_needing_root(outputs: str) -> None:
    """Learning you mistyped a flag should not first require obtaining root.

    A valid command line refused for want of privilege is 3, a bad one is 2, and
    which you get does not depend on who you are.
    """
    valid_but_unprivileged = run(
        "--mode", "host",
        "--host", str(HOST_EXAMPLE),
        "--project-a-outputs", outputs,
        "--project-b-outputs", outputs,
    )  # fmt: skip
    assert valid_but_unprivileged.returncode == 3
    assert "requires root" in valid_but_unprivileged.stderr

    assert run("--mode", "host", "--host", "/nonexistent.yaml").returncode == 2


@pytest.mark.parametrize(
    "flag",
    [
        "--rotated-from-file",
        "--rotated-authenticator-from-file",
        "--rotated-docs-from-file",
        "--rotated-jwt-from-file",
    ],
)
def test_a_rotation_file_that_does_not_exist_is_refused_before_root(
    outputs: str, flag: str
) -> None:
    """The inputs whose absence would otherwise be discovered as a skip.

    Each of these admits a proof that is unrunnable without it. A path typo
    would leave the proof skipped and the operator believing the rotation had
    been measured -- and a skip is exactly what the flag's *absence* means, so
    the two states are indistinguishable in the output. A named file that is not
    there is therefore an argument error, refused before root is demanded and
    before anything runs.

    Parametrized over the flags rather than over a constant in the gate: a
    fourth declaration added to the script and not to this list is a declaration
    with no such check, and the list is short enough to read.
    """
    result = run(
        "--mode", "host",
        "--host", str(HOST_EXAMPLE),
        "--project-a-outputs", outputs,
        "--project-b-outputs", outputs,
        flag, "/nonexistent-credential",
    )  # fmt: skip
    assert result.returncode == 2
    assert "/nonexistent-credential" in result.stderr


def test_every_rotation_declaration_is_its_own_flag(source: str) -> None:
    """One variable per credential, and the reason it is not one flag.

    A window rotates one credential at a time. A single ``--rotated`` would
    admit all three proofs on the strength of whichever was actually rotated,
    and two of the three would then compare a value against itself -- which is
    the false declaration each of those tests is written to refuse, arriving
    through the gate rather than through the operator.
    """
    for variable in (
        "APG_ROTATED_AUTHENTICATOR_FROM_FILE",
        "APG_ROTATED_DOCS_FROM_FILE",
        "APG_ROTATED_JWT_FROM_FILE",
    ):
        assert f"export {variable}=" in source, f"{variable} is never exported to the suite"


# ---------------------------------------------------------------------------
# External mode: a vantage point, and a way in
# ---------------------------------------------------------------------------


def test_external_mode_requires_a_public_address(outputs: str) -> None:
    result = run("--mode", "external", "--project-a-outputs", outputs)
    assert result.returncode == 2
    assert "--public-ipv4" in result.stderr


def test_external_mode_requires_an_ssh_destination(outputs: str) -> None:
    """Without it DX-DB-001 and DX-DB-002 skip, and a skip is not a pass.

    The same refusal shape as ``--project-b-outputs`` on the host: the run would
    otherwise do all its work and then report ``connection_tooling`` as
    ``not_run``, which is a correct verdict delivered as late as possible.
    """
    result = run(
        "--mode", "external",
        "--public-ipv4", "203.0.113.1",
        "--project-a-outputs", outputs,
    )  # fmt: skip
    assert result.returncode == 2
    assert "--ssh-destination" in result.stderr


def test_external_mode_says_where_it_must_be_run_from(source: str) -> None:
    """Not enforceable -- the host could sit behind the operator's own NAT -- so
    it is stated twice: in the help, and again as the mode starts.

    The second one matters more. A gate run from the wrong place still passes,
    and the notice is the only thing between that and an evidence file asserting
    a boundary nobody looked at from outside.
    """
    assert "MUST run from a network" in run("--help").stdout
    started = source.split("mode_external()", 1)[1]
    assert "measures its own" in started
    assert started.index("routing table") < started.index('run_suite "external"')


# ---------------------------------------------------------------------------
# The claims this gate is answerable for
# ---------------------------------------------------------------------------


def test_the_gate_resolves_claims_for_its_own_session(source: str) -> None:
    """One CLAIMS table serves four gates, so each must name its session.

    Without it this gate would resolve every claim in the table, including ones a
    later session introduces, and report them as unproved (ADR 0039).
    """
    assert "readonly SESSION=5" in source
    assert "static_nodeids_for_mode(sys.argv[1], int(sys.argv[2]))" in source
    assert 'claim_static_nodeids "${mode}" "${SESSION}"' in source


def test_the_previous_gate_still_names_its_own_session() -> None:
    """Guard the guard: a fifth gate must not have taken the fourth one's.

    This gate is derived from the Session 4 one by copying it, which is what
    D132 asks for -- and copying is exactly how a session number gets left
    behind. The two assertions are deliberately in different files.
    """
    assert "readonly SESSION=4" in SESSION_PREVIOUS.read_text(encoding="utf-8")


def test_both_environments_carry_a_claim() -> None:
    """The reason external mode exists again, stated as the table sees it.

    If Session 4's external claims were ever removed, this gate's third mode
    would go back to being a run that measures something and records nothing --
    which is the state D45 refused in Session 3.
    """
    assert claims.claims_for_mode("host", SESSION), "the host half carries no claim"
    assert claims.claims_for_mode("external", SESSION), "the external half carries no claim"


def test_the_gate_tells_the_operator_a_half_is_not_the_document(source: str) -> None:
    """Both halves are required, and the gate says so where it is read.

    The writer refuses a single half for a session with an external claim, but
    that refusal arrives after both a deploy and a scan. Saying it at the end of
    each mode costs nothing and arrives in time to be useful.
    """
    assert source.count("This is one half.") == 2
    assert "--external-input evidence/session-05-external.json" in run("--help").stdout


def test_an_empty_static_list_is_not_read_as_an_absent_claim(source: str) -> None:
    """ADR 0045's mechanism, in the one place it could be got wrong.

    Sessions 2 and 3 print "No claim is measured in this mode" when the resolver
    returns nothing, and there it is true. In Session 4 the external mode carries
    two claims whose every proof is marked ``external`` and therefore already ran
    -- an empty list means "nothing further to run", not "nothing to record", and
    a gate that skipped writing evidence on it would drop a measured claim.
    """
    body = source.split("run_claim_proofs()", 1)[1]
    assert "No claim is measured" not in body
    assert "carries its own marker" in body


# ---------------------------------------------------------------------------
# It verifies, and a partial run says nothing
# ---------------------------------------------------------------------------


def test_the_gate_deploys_nothing(source: str) -> None:
    """D20. A gate that deploys what it measures cannot be re-run to confirm a
    fix, and its result depends on whether it was the first run."""
    executable = _executable_lines(source)
    for forbidden in ("./deploy.sh", "bin/project-runtime.sh", "bin/materialize-secrets"):
        assert forbidden not in executable, f"the gate invokes {forbidden}"


@pytest.mark.parametrize("mode", ["host", "external"])
def test_a_filtered_run_writes_no_evidence(source: str, mode: str) -> None:
    body = source.split(f"mode_{mode}()", 1)[1]
    assert "evidence_is_supportable" in body
    assert body.index("evidence_is_supportable") < body.index("write_evidence"), (
        f"the -k guard runs after {mode} mode writes its evidence"
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
    assert "Use ./deploy.sh --through-session 4" not in executable
    assert 'run_suite "live_host"' in executable
