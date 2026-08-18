"""The Session 7 gate, derived from Session 6's and answering one more flag.

**Derived rather than written fresh, and that is the decision.** The Session 6
gate carries four findings that each cost a run to learn -- the marker-not-path
sweep (D211), fixture *currency* rather than existence (D212), the sentinel flag
nobody passed (D213), and the evidence-ownership handback. A gate written from
the plan's description would have lost all four, and D316's instruction is
literally "in `session-06-check.sh`'s shape".

So this module is Session 6's contract with the session number moved and one
addition, and the addition is the point.

**Session 7's third refusal is `--bucket` and `--r2-token`.** The gate never
names a bucket and never holds an R2 credential: what it measures is what the
DEPLOYMENT holds, read from inside the containers that hold it. A gate given a
bucket would be measuring the bucket somebody typed. And there is no credential
for it to be given that could administer one -- ADR 0110 puts that outside this
repository entirely.

The original Session 6 header follows, because every word of it still applies.

---

The Session 7 gate, and the two Run 10 findings built into its shape.

``bin/session-07-check.sh`` takes the shape Sessions 2 through 5 already had
(D45, D82, D132, D221): verify-only, three modes, ``--project-*-outputs`` naming
*deployed* documents rather than manifests, ``-k`` writing no evidence. What is
this module's content is the difference.

**A third runbook flag is answered by name.** The plan's shape for this gate was
``--project project.yaml --peer-project tests/fixtures/projects/project-b.yaml``.
Sessions 4 and 5 already answer ``--capabilities`` and ``--external-probe``;
``--peer-project`` joins them, because an operator reading the runbook is asking
a reasonable question and the answer is a different flag, not a usage error.

**Two findings become mechanism rather than lore.** ``--sentinel-file`` and the
new ``--admin-password-file`` are written into the documented command, not
described beneath it -- D213 recorded thirteen secret proofs gated on a flag
nobody passed for an entire session. And the rendered fixtures are checked for
*currency* rather than existence, by asking the module that already owns that
question rather than by a second implementation (D212, ADR 0073).

**The gate selects by MARKER and never by path** (D211). The sweep everyone had
been using was ``pytest tests/deployment -m live_host``, which selects by path,
so ``tests/security/`` was a directory it never reached. Five green host runs
were five reports about a subset nobody had stated the boundary of.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from agentic_postgres import REPO_ROOT
from agentic_postgres import evidence_claims as claims

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCRIPT = REPO_ROOT / "bin" / "session-07-check.sh"
SESSION_PREVIOUS = REPO_ROOT / "bin" / "session-05-check.sh"

SESSION = 6


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
        ["git", "ls-files", "--stage", "--", "bin/session-07-check.sh"],
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
# The runbook's flags, answered rather than rejected as typos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flag", "answer"),
    [
        ("--capabilities", "deployed documents"),
        ("--external-probe", "--public-ipv4"),
        ("--peer-project", "--project-b-outputs"),
    ],
)
def test_the_runbook_flags_are_answered_by_name(flag: str, answer: str) -> None:
    """Three now, and the third is this session's (D221).

    "unknown argument" would send an operator who read the plan looking for a
    typo instead of at the answer.
    """
    result = run(flag, "value")
    assert result.returncode == 2
    assert answer in result.stderr


def test_the_peer_project_answer_says_why_the_other_flag_differs() -> None:
    """Not merely a redirect. `--peer-project` names a MANIFEST and
    `--project-b-outputs` names a DEPLOYED document, and an operator told only
    "use the other one" would pass the manifest to it."""
    result = run("--peer-project", "project-b.yaml")
    assert result.returncode == 2
    assert "DEPLOYED" in result.stderr or "deployed" in result.stderr


# ---------------------------------------------------------------------------
# Host mode: two projects, or nothing
# ---------------------------------------------------------------------------


def test_host_mode_without_project_b_is_an_argument_error(outputs: str) -> None:
    """`project_isolation` is a claim about two projects' identity planes.

    With one project every proof of it would skip, the claim would resolve
    `not_run`, and the run would report that as a failure anyway -- after doing
    all the work.
    """
    result = run(
        "--mode",
        "host",
        "--host",
        str(REPO_ROOT / "host.example.yaml"),
        "--project-a-outputs",
        outputs,
    )
    assert result.returncode == 2
    assert "--project-b-outputs" in result.stderr


def test_argument_errors_are_reported_without_needing_root(outputs: str) -> None:
    """Arguments before privilege. An operator iterating on a command line
    should learn they mistyped a flag without first having to obtain root."""
    result = run(
        "--mode", "host", "--host", "/nonexistent/host.yaml", "--project-a-outputs", outputs
    )
    assert result.returncode == 2
    assert "requires root" not in result.stderr


@pytest.mark.parametrize(
    "flag",
    [
        "--sentinel-file",
        "--admin-password-file",
        "--rotated-authenticator-from-file",
        "--rotated-docs-from-file",
        "--rotated-jwt-from-file",
    ],
)
def test_a_named_file_that_does_not_exist_is_refused_before_root(flag: str, outputs: str) -> None:
    """A path with a typo in it must not be discovered after `sudo`.

    Otherwise it is found by a suite that *skips* the proof the flag exists to
    admit -- and a skip is indistinguishable from the honest reading of the
    flag's absence, which is "that did not happen in this run".
    """
    result = run(
        "--mode",
        "host",
        "--host",
        str(REPO_ROOT / "host.example.yaml"),
        "--project-a-outputs",
        outputs,
        "--project-b-outputs",
        outputs,
        flag,
        "/nonexistent/value",
    )
    assert result.returncode == 2
    assert "/nonexistent/value" in result.stderr


# ---------------------------------------------------------------------------
# D213 — the flags are in the command, not under it
# ---------------------------------------------------------------------------


def test_the_documented_command_passes_the_flags_that_admit_proofs(source: str) -> None:
    """The finding, as a property of the file rather than as a habit.

    Thirteen secret proofs were gated on `--sentinel-file` and it was not passed
    once in an entire session. The repair is not a louder paragraph: it is that
    the command an operator copies already carries the flag.

    Asserted against the usage HEREDOC only -- finding the string anywhere in
    the script would be satisfied by the argument parser, which necessarily
    names every flag it accepts.
    """
    usage = re.search(r"usage\(\) \{\n  cat <<'USAGE'\n(.*?)\nUSAGE\n", source, re.DOTALL)
    assert usage, "the usage heredoc could not be located"
    body = usage.group(1)

    command = body.split("  --mode offline")[0]
    for flag in ("--sentinel-file", "--admin-password-file"):
        assert flag in command, (
            f"{flag} is described but not present in the documented command. A flag "
            "mentioned under a command is a flag that does not get passed (D213)"
        )


def test_the_sentinel_path_is_derived_in_the_documented_command(source: str) -> None:
    """And derived, not typed: the generation directory changes on every start,
    so a hard-coded path silently names a superseded generation."""
    assert "active-secret-generation.json" in source, (
        "the documented command hard-codes a generation path instead of deriving it"
    )


# ---------------------------------------------------------------------------
# D212 — currency, not existence, and from one authority
# ---------------------------------------------------------------------------


def test_the_fixture_check_asks_the_module_that_owns_the_question(source: str) -> None:
    """A shell reimplementation would be a second opinion, and the second one is
    always the permissive one -- the duplicate-plus-test shape D175 and D260 have
    both already cost this project."""
    assert "rendered_fixtures" in source, (
        "the gate decides fixture staleness for itself instead of asking "
        "tests/contract/rendered_fixtures.py, which already distinguishes "
        "absent from stale from current"
    )


def test_absent_fixtures_are_a_gate_failure_rather_than_a_skip(source: str) -> None:
    """The gate refuses where the suite skips, and the difference is deliberate.

    For a test module, absent fixtures mean a dependency is missing and skipping
    is honest. For a gate they mean the compose-model proofs did not run, and
    the gate would exit 0 having measured less than it reports.
    """
    assert re.search(r"absent\|stale\)", source), (
        "the gate does not treat absent fixtures the same as stale ones"
    )


# ---------------------------------------------------------------------------
# D211 — the selector is a marker, never a path
# ---------------------------------------------------------------------------


def test_the_host_sweep_selects_by_marker_and_names_no_directory(source: str) -> None:
    """`pytest tests/deployment -m live_host` selects by PATH.

    `tests/security/` is then a directory it never reaches, and five green host
    runs were five reports about a subset nobody had stated the boundary of.
    """
    assert re.search(r'run_suite "live_host"', source), "the host mode does not sweep by marker"

    # Checked against `run_suite`'s BODY, which is the one place a marker sweep
    # is built, rather than against the whole file. Two earlier spellings of
    # this test were wrong in opposite directions, and both are worth recording:
    #
    #   * scanning the file for "pytest ... tests/deployment" failed against a
    #     correct gate, because the gate's own commentary quotes the defective
    #     command in order to explain it. A scan that cannot tell an instruction
    #     from a description of one reports documentation as a defect;
    #   * scanning for any path would have flagged offline mode's deliberate
    #     `pytest -q tests/contract/test_acceptance_registry.py`, which names one
    #     module on purpose and excludes nothing, because it is not a sweep.
    #
    # The property is narrower than either: the run that produces the evidence
    # selects by marker and passes no path at all.
    body = re.search(r"^run_suite\(\) \{\n(.*?)^\}", source, re.DOTALL | re.MULTILINE)
    assert body, "run_suite could not be located"
    assert "tests/" not in body.group(1), (
        "the marker sweep names a path; that selects by directory and silently "
        f"excludes every module outside it (D211):\n{body.group(1)}"
    )


# ---------------------------------------------------------------------------
# Claims and evidence
# ---------------------------------------------------------------------------


def test_the_gate_resolves_claims_for_its_own_session(source: str) -> None:
    assert "readonly SESSION=7" in source
    assert "session-05" not in source.replace("session-05-check.sh", ""), (
        "a Session 5 filename survived the copy; the gate would write the previous "
        "session's evidence while its --help named files it never writes"
    )


def test_the_previous_gate_still_names_its_own_session() -> None:
    """Copying a gate must not edit the one it was copied from."""
    assert "readonly SESSION=5" in SESSION_PREVIOUS.read_text(encoding="utf-8")


def test_both_environments_carry_a_claim() -> None:
    """A mode that carries no claim would write evidence asserting nothing."""
    for mode in ("host", "external"):
        assert claims.claims_for_mode(mode, SESSION), f"{mode} carries no claim in session 6"


def test_the_gate_tells_the_operator_a_half_is_not_the_document(source: str) -> None:
    assert source.count("This is one half.") == 2, (
        "one of the two evidence-writing modes does not say it produced a half"
    )


def test_a_filtered_run_writes_no_evidence(source: str) -> None:
    """`-k` is for iterating on one failure. Evidence from a filtered run would
    report a claim on the strength of whichever tests the expression matched."""
    assert "evidence_is_supportable" in source
    assert source.count("announce_no_evidence") == 3


def test_the_gate_deploys_nothing(source: str) -> None:
    """A gate that deploys cannot be re-run to confirm a fix (D20)."""
    for forbidden in ("./deploy.sh --host", "project-runtime.sh", "materialize-secrets"):
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            assert forbidden not in stripped, f"the gate runs {forbidden!r}: {stripped}"


def test_an_empty_static_list_is_not_read_as_an_absent_claim(source: str) -> None:
    """`pytest` with no node IDs collects the entire suite, which is the most
    expensive possible way to measure nothing."""
    assert "carries its own marker" in source


def test_the_gate_refuses_a_bucket_and_a_credential(source: str) -> None:
    """Session 7's third refusal (D316), and it is not only a naming courtesy.

    `--bucket` and `--r2-token` are refused by name because both are things an
    operator might reasonably expect a storage gate to take, and the answer to
    both is that the gate does not work that way.

    **The gate reads the bucket from the deployment**, out of the container that
    holds it, because what a container holds is what a container holds (D76,
    D306). A gate handed a bucket name would be measuring the name somebody
    typed, and would pass against a deployment pointed somewhere else entirely.

    **And there is no credential to hand it.** ADR 0110 puts the credential that
    can administer a bucket outside this repository: it is a Cloudflare API
    token a human holds, and no process here has one. A flag that accepted one
    would be the first place in this system that could.
    """
    for flag in ("--bucket", "--r2-token"):
        assert f"      {flag}|" in source or f"|{flag}|" in source or f"|{flag})" in source, (
            f"{flag} is not answered by name; an operator passing it gets a bare "
            "usage error rather than the reason"
        )
    assert "there is no --bucket and no --r2-token" in source


def test_the_gate_takes_no_flag_that_could_carry_a_credential(source: str) -> None:
    """D105 at the gate, keyed on the arms that BIND A VALUE.

    `test_no_command_documents_a_secret_argument` reads `--help`, which catches
    a documented flag. This reads the parser, which catches an undocumented one.

    **Two narrowings, and each was forced by the scan being wrong.** The first
    version scanned every `--word` in the file and fired on `--r2-token`, which
    this gate names precisely in order to refuse it. The second excluded any
    case arm whose body called `die` -- and that swallowed almost every real
    flag, because `--mode` and its neighbours validate with
    `[ "$#" -ge 2 ] || die 2 "--mode requires a value."`. A refusal and a
    validation both call `die`.

    So the discriminator is the one that matches the property being asserted:
    an arm can carry a credential only if it **binds `$2`**. A flag that takes
    no value cannot carry one, and a flag that is refused never reaches a value
    at all. That is narrower than either earlier attempt and it is narrower for
    a reason rather than to get past a failure.

    The `--*-file` shape is what this project uses when a value must not be an
    argument: the flag names a path, and the file is read by the process rather
    than by the shell that invoked it.
    """
    binding: set[str] = set()
    for patterns, body in re.findall(
        r"^ {6}(--[^)\n]+)\)\n((?:.*\n)*?) {8};;$", source, re.MULTILINE
    ):
        if '="$2"' not in body:
            continue
        binding.update(re.findall(r"--[a-z][a-z0-9-]+", patterns))

    assert "--mode" in binding, (
        f"the parser scan did not find --mode among the value-taking flags "
        f"({sorted(binding)}), so it is not reading the parser"
    )

    for flag in sorted(binding):
        if flag.endswith("-file"):
            continue
        assert not any(
            word in flag for word in ("password", "secret", "token", "key", "credential")
        ), (
            f"{flag} binds a value and looks like it carries a credential. An argument "
            "is visible in ps, in /proc/<pid>/cmdline and to any audit rule watching "
            "execve; this project passes a path instead (D105)"
        )


def test_the_credential_flag_scan_would_catch_a_real_one() -> None:
    """Guard the guard, because the scan has now been narrowed twice.

    Three arms, one per way the scan could be wrong: a flag that binds a
    credential is caught; the same name in a REFUSING arm is not; and a flag
    that binds nothing is not. Without all three, a narrowing is indistinguishable
    from an exemption.
    """

    def binding_flags(source: str) -> set[str]:
        found: set[str] = set()
        for patterns, body in re.findall(
            r"^ {6}(--[^)\n]+)\)\n((?:.*\n)*?) {8};;$", source, re.MULTILINE
        ):
            if '="$2"' not in body:
                continue
            found.update(re.findall(r"--[a-z][a-z0-9-]+", patterns))
        return found

    binds = '      --api-token)\n        TOKEN="$2"\n        shift 2\n        ;;\n'
    refuses = '      --api-token)\n        die 2 "there is no --api-token."\n        ;;\n'
    valueless = "      --api-token)\n        SEEN=1\n        shift\n        ;;\n"

    assert "--api-token" in binding_flags(binds)
    assert "--api-token" not in binding_flags(refuses)
    assert "--api-token" not in binding_flags(valueless)
