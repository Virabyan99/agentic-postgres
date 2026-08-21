"""The Session 8 gate, derived from Session 7's and answering three more flags.

**Derived rather than written fresh, and that is the decision.** The Session 6
and 7 gates carry findings that each cost a run to learn -- the marker-not-path
sweep (D211), fixture *currency* rather than existence (D212), the sentinel flag
nobody passed (D213), the evidence-ownership handback, and the refusal of flags
that would let a gate measure something an operator typed. A gate written from
the plan's description would have lost all of them, and D404's instruction is
literally "in `session-07-check.sh`'s shape".

**Session 8's own additions are four.**

*Three refusals.* `--capability-lock` and `--agent-token` join `--capabilities`,
`--project` and `--peer-project`, because both are things an operator might
reasonably expect an agent-plane gate to take and the answer to both is that it
does not work that way. The plane obeys the lock **mounted into its container**
(ADR 0126); the suite creates its own agent through the product's own
`auth_create_agent` and obtains a token from the deployment. A gate given either
would be measuring the file or the credential somebody typed.

*One precondition.* `check_agent_plane_is_published` reads the deployed document
before anything runs. D326's two-stage convergence means the deploy that FIRST
starts an MCP container publishes `routes.mcp: unavailable` -- correctly -- and
the redeploy publishes `ready`. Without the check, forty proofs fail on a
connection error and the operator reads forty tracebacks to learn one thing.

**And this module fixes the thing the Session 7 module got wrong about itself**
(D459). That file asserts `both_environments_carry_a_claim` with `SESSION = 6`,
a constant left behind when it was copied from Session 6 -- so the test written
to check that a gate names its own session was itself in the wrong session, and
it passed on Session 4's inherited `transport_boundary` regardless of whether
Session 7 had an external claim at all. The version here asserts the session's
**own** claims, which is the property the name has always described.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from agentic_postgres import REPO_ROOT
from agentic_postgres import evidence_claims as claims

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCRIPT = REPO_ROOT / "bin" / "session-08-check.sh"
SESSION_PREVIOUS = REPO_ROOT / "bin" / "session-07-check.sh"

SESSION = 8

#: The claims Session 8 introduced, by mode. Written out rather than derived
#: from `claims_for_mode`, which would be the mechanism checking itself and
#: would pass for every possible claim table (D260's second mutation).
SESSION_EIGHT_CLAIMS = {
    "host": (
        "agent_authentication",
        "agent_budgets",
        "agent_credentials",
        "agent_query_construction",
        "agent_reads",
        "agent_scopes",
        "agent_surface",
    ),
    "external": ("public_agent_boundary",),
}


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
        ["git", "ls-files", "--stage", "--", "bin/session-08-check.sh"],
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
        ("--peer-project", "--project-b-outputs"),
        ("--project", "DEPLOYED"),
        ("--capability-lock", "container"),
        ("--agent-token", "auth_create_agent"),
    ],
)
def test_the_runbook_flags_are_answered_by_name(flag: str, answer: str) -> None:
    """Five now, and three are this session's (D404).

    "unknown argument" would send an operator who read the plan looking for a
    typo instead of at the answer. D404 records that the runbook family has
    proposed the wrong invocation for this gate **twice** -- D316 is the same
    row from Session 7 -- so the answer is written into the parser rather than
    left to a reader.
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


def test_the_agent_token_refusal_says_where_the_token_comes_from() -> None:
    """The refusal has to answer the question behind the flag.

    An operator reaching for `--agent-token` is asking "how does the gate get a
    token?", and "there is no such flag" leaves them minting one -- which would
    prove that this suite can sign, not that the deployment issues tokens an
    agent plane accepts.
    """
    result = run("--agent-token", "eyJ...")
    assert result.returncode == 2
    assert "obtains a token from the deployment" in result.stderr


# ---------------------------------------------------------------------------
# Host mode: two projects, or nothing
# ---------------------------------------------------------------------------


def test_host_mode_without_project_b_is_an_argument_error(outputs: str) -> None:
    """`project_isolation` is a claim about two projects' identity planes.

    Session 8 gives it a second job: the agent plane's cross-project refusal is
    a refusal of a REAL peer with its own key set, issuer and audience, which is
    a sharper negative than a garbage string.
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
    assert "rendered_fixtures" in source


def test_absent_fixtures_are_a_gate_failure_rather_than_a_skip(source: str) -> None:
    """The gate refuses where the suite skips, and the difference is deliberate."""
    assert re.search(r"absent\|stale\)", source)


def test_the_fixture_failure_says_to_re_render_on_the_host(source: str) -> None:
    """**D383.** `.generated/` is gitignored and is never transported.

    An operator who re-renders on the workstation and transports the bundle
    arrives on the host with fixtures that are still absent, and the gate says
    `stale` again for a reason the message did not name.
    """
    assert "ON THE HOST" in source or "on the host" in source.lower().replace("_", " ")


# ---------------------------------------------------------------------------
# D211 — the selector is a marker, never a path
# ---------------------------------------------------------------------------


def test_the_host_sweep_selects_by_marker_and_names_no_directory(source: str) -> None:
    """`pytest tests/deployment -m live_host` selects by PATH.

    `tests/security/` is then a directory it never reaches, and five green host
    runs were five reports about a subset nobody had stated the boundary of.

    Checked against `run_suite`'s BODY rather than the whole file: the gate's
    own commentary quotes the defective command in order to explain it, and a
    scan that cannot tell an instruction from a description of one reports
    documentation as a defect.
    """
    assert re.search(r'run_suite "live_host"', source), "the host mode does not sweep by marker"

    body = re.search(r"^run_suite\(\) \{\n(.*?)^\}", source, re.DOTALL | re.MULTILINE)
    assert body, "run_suite could not be located"
    assert "tests/" not in body.group(1), (
        "the marker sweep names a path; that selects by directory and silently "
        f"excludes every module outside it (D211):\n{body.group(1)}"
    )


# ---------------------------------------------------------------------------
# The agent plane's own precondition
# ---------------------------------------------------------------------------


def test_the_gate_refuses_a_deployment_whose_agent_plane_is_not_published(source: str) -> None:
    """Checked before the suite, so one message replaces forty tracebacks.

    And the message names D326's two-stage convergence, because `unavailable` on
    the first deploy is the system working rather than a fault: the deploy that
    starts an MCP container observes the route before the edge has attached it.
    An operator told only "not ready" would go looking for a defect.
    """
    assert "check_agent_plane_is_published" in source
    assert "DEPLOY AGAIN" in source, (
        "the precondition does not tell the operator what to do about the ordinary case"
    )
    assert "D326" in source


def test_the_precondition_runs_in_both_modes_that_measure_a_deployment(source: str) -> None:
    """Host and external both read a served plane, so both need the check.

    External needs it for a reason of its own: without a published route the
    boundary proofs would report "closed" for a surface that was never open,
    which is a fact about the deployment rather than about the boundary.
    """
    assert source.count('check_agent_plane_is_published "${PROJECT_A_OUTPUTS}"') == 2


def test_the_precondition_refuses_a_route_that_is_a_bare_string(source: str) -> None:
    """**D395**, from the other side.

    `routes.mcp` was a string in every rendered document since outputs v1 and
    absent from every deployed one. A gate that accepted a string would pass
    against a deployment that predates v12 -- and `evidence.py` would then
    refuse the document later, after the whole suite had run.
    """
    assert "not a published-route object" in source
    assert "REDEPLOY" in source


def test_the_precondition_actually_refuses_rather_than_merely_naming_a_message(
    tmp_path,
) -> None:
    """**The arm the other three were missing.** It runs the check.

    The three tests above assert that the gate's source contains the right
    sentences. That is D277's shape: *an AST scan asking whether a function is
    mentioned is satisfied by dead code*. A battery arm that replaced
    `if not isinstance(route, dict):` with `if False:` left every one of them
    green, because the message it stops printing is still in the file.

    Run through **external** mode, which reaches the precondition at step 1 and
    needs neither root nor a TTY. Three documents, and the third is the CONTROL:
    without it, "the gate exits 6" is equally well explained by a gate that
    refuses everything.
    """
    import json

    def check(routes: dict, mcp: dict | None = None) -> subprocess.CompletedProcess[str]:
        document = tmp_path / f"outputs-{abs(hash(json.dumps(routes, sort_keys=True)))}.json"
        payload = {"schema_version": 12, "routes": routes}
        if mcp is not None:
            payload["mcp"] = mcp
        document.write_text(json.dumps(payload), encoding="utf-8")
        # `-k` selects nothing, so the CONTROL arm -- the one that gets PAST the
        # precondition -- does not then spend eighty seconds failing to reach
        # 203.0.113.1. It also stops the run writing evidence, which is exactly
        # right: this test is about step 1 and has no business producing any.
        return run(
            "--mode",
            "external",
            "--public-ipv4",
            "203.0.113.1",
            "--ssh-destination",
            "nobody@203.0.113.1",
            "--project-a-outputs",
            str(document),
            "-k",
            "apg_selects_no_test",
        )

    # D395: a bare string is what every RENDERED document has carried since
    # outputs v1, and what no deployed one carried until v12.
    string_route = check({"mcp": "https://example.test/mcp"})
    assert string_route.returncode == 6, string_route.stdout + string_route.stderr
    assert "not a published-route object" in (string_route.stdout + string_route.stderr)

    # D326: the ordinary first-deploy state, and the message has to say so.
    unavailable = check({"mcp": {"status": "unavailable", "url": None}})
    assert unavailable.returncode == 6
    assert "DEPLOY AGAIN" in (unavailable.stdout + unavailable.stderr)

    # THE CONTROL. A published route and a ready block must get PAST the
    # precondition -- it then fails later, on the suite, which is not this test's
    # business. What matters is that step 1 did not refuse it.
    served = check(
        {"mcp": {"status": "ready", "url": "https://example.test/mcp"}},
        mcp={"status": "ready", "protocol_revision": "2025-11-25"},
    )
    combined = served.stdout + served.stderr
    assert "not a published-route object" not in combined, combined
    assert "DEPLOY AGAIN" not in combined, (
        "a ready route was refused by the precondition; the two arms above would then "
        "pass against a gate that refuses every document"
    )


# ---------------------------------------------------------------------------
# Claims and evidence
# ---------------------------------------------------------------------------


def test_the_gate_resolves_claims_for_its_own_session(source: str) -> None:
    assert "readonly SESSION=8" in source
    assert "session-07" not in source.replace("session-07-check.sh", ""), (
        "a Session 7 filename survived the copy; the gate would write the previous "
        "session's evidence while its --help named files it never writes"
    )


def test_the_previous_gate_still_names_its_own_session() -> None:
    """Copying a gate must not edit the one it was copied from."""
    assert "readonly SESSION=7" in SESSION_PREVIOUS.read_text(encoding="utf-8")


def test_each_environment_carries_a_claim_this_session_introduced() -> None:
    """**D459.** Not "carries a claim" -- carries one of THIS session's.

    The Session 7 copy of this test asserted `claims_for_mode(mode, 6)`, a
    constant left behind when the module was copied from Session 6. So it passed
    on Session 4's inherited `transport_boundary` no matter what Session 7 did,
    and the test written to check that a gate names its own session was itself
    in the wrong one.

    Claims are cumulative, so "this mode carries something" is true from Session
    4 onward and cannot fail. The expectation is written out above rather than
    derived from `claims_for_mode`, which would be the mechanism checking itself.
    """
    for mode, expected in SESSION_EIGHT_CLAIMS.items():
        resolved = set(claims.claims_for_mode(mode, SESSION))
        missing = sorted(set(expected) - resolved)
        assert not missing, (
            f"{mode} mode does not carry Session 8's own claims {missing}. The gate "
            "would write a half that is silent about them, and the merge would refuse"
        )


def test_the_expectation_table_names_every_claim_this_session_introduced() -> None:
    """**Guard the guard.** Otherwise a row can be deleted to make the test pass.

    `SESSION_EIGHT_CLAIMS` is written out rather than derived, which is right --
    a table computed from `claims_for_mode` would be the mechanism checking
    itself. The cost of writing it out is that shortening it is invisible: a
    battery arm that removed `agent_surface` left the assertion above green.

    This is the same hole `test_every_claim_is_declared_here` closes for
    `CLAIM_INTRODUCED_IN`, and it is closed the same way: the table and the
    claim set have to name the same things.
    """
    declared = {claim for group in SESSION_EIGHT_CLAIMS.values() for claim in group}
    introduced = {claim for claim in claims.CLAIMS if claims.claim_session(claim) == SESSION}
    assert declared == introduced, (
        "the expectation table and the claims introduced in this session disagree: "
        f"only in the table {sorted(declared - introduced)}, "
        f"only in CLAIMS {sorted(introduced - declared)}"
    )


def test_every_session_eight_claim_belongs_to_session_eight() -> None:
    """ADR 0089. A claim built from an earlier session's id moves, silently.

    `claim_session` is a `max()`, so one older requirement id mixed into a
    Session 8 claim either drags it into an earlier gate's evidence -- turning
    that session's document red -- or hides it from this one entirely. Neither
    failure produces an error.
    """
    for expected in SESSION_EIGHT_CLAIMS.values():
        for claim in expected:
            assert claims.claim_session(claim) == SESSION, (
                f"{claim} resolves to session {claims.claim_session(claim)}, not {SESSION}"
            )


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


def test_offline_mode_checks_the_compiled_capability_contract(source: str) -> None:
    """Session 8's own offline addition, and the check path holds no writer.

    `bin/mcp-contract.sh check` is what keeps `capabilities.example.yaml` and
    the committed canonical contract in step. A gate that ran `compile` instead
    would rewrite the artefact it was measuring and could never fail.
    """
    assert "bin/mcp-contract.sh check" in source
    assert "mcp-contract.sh compile" not in source
    assert "mcp-contract.sh lock" not in source


def test_the_gate_takes_no_flag_that_could_carry_a_credential(source: str) -> None:
    """D105 at the gate, keyed on the arms that BIND A VALUE.

    An arm can carry a credential only if it binds `$2`. A flag that takes no
    value cannot carry one, and a flag that is refused never reaches a value at
    all -- which is why `--agent-token`, named here precisely in order to be
    refused, must not trip this.

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
    assert "--agent-token" not in binding, (
        "--agent-token binds a value; it is named in order to be REFUSED"
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
