"""The Session 22 gate, and the first offline mode that produces evidence.

**Derived from `test_session_eight_gate_modes.py`**, which is the most recent
module of this family -- Sessions 20 and 21 added gates and no guard of their
own, and `grep -l "session-21-check" tests/contract` named only
`test_cli_contract.py`. What is carried over is the shape that generalises: a
gate is executable in the index, answers all three modes, refuses an unknown
one, names its OWN session's claims rather than an inherited one (D459), and
deploys nothing. What is dropped is everything about Session 8's flags, which
`test_session_eight_gate_modes.py` still guards on the file that has them.

**What is new here is the whole reason the module exists.** Session 22's gate
is the first whose offline mode writes a half, and three things follow from
that, each of which could go wrong quietly:

* the half must be written from the run that selected everything, not from a
  second differently-selected one;
* the half must pass NO deployed document, because it measures a checkout --
  the writer refuses one, and a gate that passed one would be describing a
  deployment it never read;
* and the offline mode must REFUSE when docker is absent rather than let the
  cluster proofs skip. A skip is not a pass: the half would be written, the
  claim would be `not_run`, and the gate would exit 5 having produced a
  document that looks like evidence of a command nobody ran.

The source-reading tests read `bin/session-22-check.sh` as text, which is the
right instrument for a shell script's structure and the wrong one for its
behaviour -- so the two argument tests below actually RUN it.
"""

from __future__ import annotations

import subprocess

import pytest

from agentic_postgres import REPO_ROOT
from agentic_postgres import evidence_claims as claims

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCRIPT = REPO_ROOT / "bin" / "session-22-check.sh"
SESSION_PREVIOUS = REPO_ROOT / "bin" / "session-21-check.sh"

SESSION = 22

#: The claims Session 22 introduced, by mode. Written out rather than derived
#: from `claims_for_mode`, which would be the mechanism checking itself and
#: would pass for every possible claim table (D260's second mutation).
#:
#: `external` is absent and that is the assertion: a disposable cluster on a
#: developer's own machine publishes on 127.0.0.1, and inventing an external
#: claim to make the shape symmetric is what ADR 0065 refuses.
SESSION_TWENTY_TWO_CLAIMS = {
    "offline": ("dev_environment", "dev_isolation", "dev_churn", "offline_evidence"),
    "host": ("plane_confirmed_count", "agent_tenant_read"),
}


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args], capture_output=True, text=True, check=False, cwd=REPO_ROOT
    )


def code(text: str) -> str:
    """The script with its comment lines removed.

    **A scan that reads prose measures prose** (D277, and D1197 in this run).
    The battery replaced `docker version` with `true # docker version` and the
    docker assertion below SURVIVED, because the comment still carried the words
    the test was looking for. This gate explains at length what each step does,
    so almost every name a structural test wants to find is also in a sentence
    about it -- which makes the comment-stripped text the only honest instrument
    for "does this script DO x".
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def body_of(text: str, name: str) -> str:
    """One shell function's body, comments removed."""
    body = text[text.index(f"{name}() {{") :]
    return code(body[: body.index("\n}\n")])


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
        ["git", "ls-files", "--stage", "--", "bin/session-22-check.sh"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.startswith("100755 "), result.stdout.strip()


def test_help_exits_zero_and_names_all_three_modes() -> None:
    result = run("--help")
    assert result.returncode == 0, result.stdout + result.stderr
    for mode in ("--mode offline", "--mode host", "--mode external"):
        assert mode in result.stdout, mode


def test_a_missing_mode_is_an_argument_error() -> None:
    result = run()
    assert result.returncode == 2
    assert "--mode is required" in result.stderr


def test_an_unknown_mode_names_the_three_that_exist() -> None:
    result = run("--mode", "hostile")
    assert result.returncode == 2
    for mode in ("offline", "host", "external"):
        assert mode in result.stderr, result.stderr


def test_the_gate_resolves_claims_for_its_own_session(source: str) -> None:
    """One session literal, and no filename from the gate it was derived from.

    D505's standing instance: eleven references to the previous session's name
    survived one diff, in the usage block an operator copies and in every
    message the gate prints about itself.
    """
    assert "readonly SESSION=22" in source
    provenance = "**Derived from bin/session-21-check.sh by diff, not retyped**"
    stale = [
        line
        for line in source.splitlines()
        if "session-21-check" in line and provenance not in line
    ]
    assert not stale, (
        f"a Session 21 filename survived the derivation: {stale}. The gate would "
        "write the previous session's evidence while its --help named files it "
        "never writes"
    )


def test_the_previous_gate_still_names_its_own_session() -> None:
    """Deriving a gate must not edit the one it was derived from."""
    assert "readonly SESSION=21" in SESSION_PREVIOUS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The offline half -- `EVD-OFFLINE-001`
# ---------------------------------------------------------------------------


def test_offline_mode_writes_the_offline_half(source: str) -> None:
    """`EVD-OFFLINE-001`. The first offline mode in this project that writes one.

    Four properties, and each is a way this could be wrong while looking right.

    **It is written.** Every earlier gate's offline mode ends by printing
    PASSED, and a Session 22 gate that did the same would close a session whose
    four own claims nothing had recorded.

    **From step 3's JUnit**, which is the run that selected everything. A half
    written from a second, narrower run is a verdict about a different
    collection of tests -- the same reason `-k` writes no evidence at all.

    **Passing no deployed document.** `write_evidence` is one function for all
    three modes precisely because two copies drifted apart once (the host
    branch gained `--project-b-outputs` and the external one did not), and the
    offline branch has to subtract rather than add: an offline half measures a
    CHECKOUT, and the writer refuses `--project-a-outputs` for it.

    **Guarded by `evidence_is_supportable`**, like the other two. A `-k` run
    that wrote an offline half would report a claim on the strength of
    whichever tests the expression happened to match.

    Goes red if: step 9 is dropped; the JUnit it reads is not the one step 3
    wrote; the offline branch starts passing a deployed document; or the `-k`
    guard is lost on this mode while the other two keep it.
    """
    stripped = code(source)
    assert 'step "9. Offline evidence"' in stripped, (
        "offline mode writes no evidence half. Session 22's own claims are "
        "measured in a checkout or nowhere"
    )
    assert "write_evidence offline" in stripped

    junit = '"${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-offline-tests.xml"'
    assert stripped.count(junit) == 1, (
        "step 3's JUnit is not kept under the offline prefix, so step 9 computes "
        f"its verdicts from something else (matched {stripped.count(junit)} times)"
    )

    branch = body_of(source, "write_evidence")
    assert '"${mode}" != "offline"' in branch, (
        "write_evidence has no offline branch, so the offline half is written "
        "with --project-a-outputs -- naming a deployment it never read"
    )
    before, after = branch.split('if [ "${mode}" != "offline" ]; then', 1)
    assert "--project-a-outputs" not in before, (
        "--project-a-outputs is passed unconditionally, so the offline branch "
        "below it changes nothing"
    )
    assert "--project-a-outputs" in after and "--project-b-outputs" in after

    offline_mode = body_of(source, "mode_offline")
    assert "evidence_is_supportable" in offline_mode and "announce_no_evidence" in offline_mode, (
        "a filtered offline run would write a half on the strength of whichever tests -k matched"
    )


def test_offline_mode_refuses_a_workstation_with_no_docker(source: str) -> None:
    """A skip is not a pass, and this is where that rule costs something.

    Every cluster fixture in the suite skips without a daemon, which was right
    while offline mode wrote nothing. Now it would write a half in which
    `dev_environment` is `not_run` -- a document that looks like evidence of a
    command nobody ran. So the daemon is a PREREQUISITE of the mode (exit 3),
    checked before the suite rather than discovered inside it, and the message
    says what is missing and what to do.

    Read as source rather than run, because running it needs a workstation with
    no docker, which is the one thing this workstation is not. What is asserted
    is the shape: the check precedes step 3, dies 3, and names the requirement
    whose proofs it protects.

    **The check is found as a COMMAND, not as a substring** (D1197). Two
    versions of this test were survived by the same mutation before it held. The
    first scanned the whole function including its comments, and this gate
    explains at length what each step does, so the sentence describing the check
    satisfied the assertion that the check exists. The second stripped comment
    LINES -- and `true # docker version` is not a comment line. What answers the
    question "does this script run `docker version`" is a line that begins with
    it, so that is what is looked for.
    """
    offline_mode = body_of(source, "mode_offline")
    lines = offline_mode.splitlines()
    checks = [i for i, line in enumerate(lines) if line.strip().startswith("docker version")]
    assert checks, (
        "offline mode does not RUN `docker version`. A mention of it in a "
        "comment, or a `docker version` that is an argument to something else, "
        "is not a check"
    )
    suites = [i for i, line in enumerate(lines) if 'step "3.' in line]
    assert suites and checks[0] < suites[0], (
        "the daemon is checked after the suite has already skipped its way past "
        "the proofs that need it"
    )
    check = "\n".join(lines[checks[0] : suites[0]])
    assert "die 3" in check, (
        "an absent daemon is reported as something other than a missing "
        "prerequisite; exit 3 is what an operator's runbook reads"
    )
    assert "DEV-ENV-001" in check, "the refusal does not name what it is protecting"
    assert "SKIP" in check or "skip" in check, (
        "the refusal does not say why an absent daemon is worse than a skip, "
        "which is the whole reason it is a refusal"
    )


def test_offline_mode_runs_the_round_trip_in_order(source: str) -> None:
    """The five verbs, in the order a developer takes them, through `apg.sh`.

    The suite exercises every verb; what this adds is the sequence, run through
    the front door rather than a fixture. `seed` after `up` because there is
    nothing to seed before it, `reset` after `seed` because what a reset must
    survive is a database with rows in it, and `down` last because a step that
    leaves a container running passes by leaking.

    And `down` FIRST, before `up`: a gate is re-run to confirm a fix, and the
    second run has to start where the first did (D20).
    """
    offline_mode = body_of(source, "mode_offline")
    round_trip = offline_mode[offline_mode.index('step "8.') :]
    round_trip = round_trip[: round_trip.index('step "9.')]

    verbs = [
        line.split("dev ", 1)[1].split()[0]
        for line in round_trip.splitlines()
        if "bin/apg.sh dev " in line
    ]
    assert verbs == ["down", "up", "status", "seed", "reset", "down"], (
        f"the round trip runs {verbs}. It starts with a teardown so a re-run "
        "starts where the first run did, and ends with one so it leaves nothing"
    )
    assert "project.example.yaml" in round_trip


def test_the_help_documents_the_three_half_merge(source: str) -> None:
    """The merge an operator copies, and the flag that is now required.

    D703's standing instance: the usage block is a quoted heredoc, so a session
    number written inside it cannot interpolate, and three derivations running
    the merge example told an operator to write an earlier session's evidence
    file. The numbers are derived; what this checks is that the THIRD input is
    in the command rather than described under it (D213).
    """
    result = run("--help")
    assert result.returncode == 0
    assert "--offline-input evidence/session-22-offline.json" in result.stdout, (
        "the merge command omits the offline half. `merge` REQUIRES it exactly "
        "when the session has offline claims, so the documented command would "
        "exit 2 for the operator who copied it"
    )
    assert "--host-input evidence/session-22-host.json" in result.stdout
    assert "--external-input evidence/session-22-external.json" in result.stdout
    assert "session-21" not in result.stdout, (
        "the previous session's evidence filenames are in the command an "
        "operator copies; running it would overwrite that session's document"
    )


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


def test_each_environment_carries_a_claim_this_session_introduced() -> None:
    """**D459.** Not "carries a claim" -- carries one of THIS session's.

    Claims are cumulative, so "this mode carries something" is true from
    Session 4 onward and cannot fail. The expectation is written out above
    rather than derived from `claims_for_mode`, which would be the mechanism
    checking itself.
    """
    for mode, expected in SESSION_TWENTY_TWO_CLAIMS.items():
        resolved = set(claims.claims_for_mode(mode, SESSION))
        missing = sorted(set(expected) - resolved)
        assert not missing, (
            f"{mode} mode does not carry Session 22's own claims {missing}. The "
            "gate would write a half that is silent about them, and the merge "
            "would refuse"
        )


def test_the_expectation_table_names_every_claim_this_session_introduced() -> None:
    """**Guard the guard.** Otherwise a row can be deleted to make the test pass.

    The same hole `test_every_claim_is_declared_here` closes for
    `CLAIM_INTRODUCED_IN`, closed the same way: the table and the claim set have
    to name the same things.
    """
    declared = {claim for group in SESSION_TWENTY_TWO_CLAIMS.values() for claim in group}
    introduced = {claim for claim in claims.CLAIMS if claims.claim_session(claim) == SESSION}
    assert declared == introduced, (
        "the expectation table and the claims introduced in this session "
        f"disagree: only in the table {sorted(declared - introduced)}, "
        f"only in CLAIMS {sorted(introduced - declared)}"
    )


def test_every_session_twenty_two_claim_belongs_to_session_twenty_two() -> None:
    """ADR 0089. A claim built from an earlier session's id moves, silently.

    `claim_session` is a `max()`, so one older requirement id mixed into a
    Session 22 claim either drags it into an earlier gate's evidence -- turning
    that session's document red -- or hides it from this one entirely. D1150 is
    the live instance: the plan had two Session 21 requirements joining Session
    16 and Session 18 claims, and the guard caught it on the first run.
    """
    for expected in SESSION_TWENTY_TWO_CLAIMS.values():
        for claim in expected:
            assert claims.claim_session(claim) == SESSION, (
                f"{claim} resolves to session {claims.claim_session(claim)}, not {SESSION}"
            )


def test_exactly_the_four_declared_claims_are_offline() -> None:
    """The declaration is the whole definition (ADR 0202), so it is asserted.

    Not "the offline mode carries some claims": the four this session decided
    to measure in a checkout, and no fifth. A claim that became offline without
    anybody deciding to is the failure the declaration exists to prevent, and
    it would be invisible in a test that only checked membership one way.
    """
    assert set(claims.OFFLINE_CLAIMS) == set(SESSION_TWENTY_TWO_CLAIMS["offline"]), (
        "OFFLINE_CLAIMS and this session's offline claims disagree: "
        f"{sorted(set(claims.OFFLINE_CLAIMS) ^ set(SESSION_TWENTY_TWO_CLAIMS['offline']))}"
    )
    for claim in SESSION_TWENTY_TWO_CLAIMS["host"]:
        assert claim not in claims.OFFLINE_CLAIMS, (
            f"{claim} is declared offline. It is about a RUNNING plane, and a "
            "checkout answering it would have reported beta green through the "
            "eight minutes it served the wrong lock (D1152)"
        )


# ---------------------------------------------------------------------------
# Inherited properties a derivation loses first
# ---------------------------------------------------------------------------


def test_a_filtered_run_writes_no_evidence(source: str) -> None:
    """`-k` is for iterating on one failure. Evidence from a filtered run would
    report a claim on the strength of whichever tests the expression matched."""
    assert "evidence_is_supportable" in source
    assert source.count("announce_no_evidence") == 4, (
        "one of the three evidence-writing modes does not announce that it wrote "
        "none, or the helper was dropped"
    )


def test_every_mode_says_its_half_is_not_the_document(source: str) -> None:
    """Three halves now, and each must say so.

    A gate printing PASSED after writing one third of a session's evidence is
    the shape an operator reads as "done". The sentence is what tells them two
    more runs are owed -- and for this session two of them are another
    session's trip.
    """
    assert source.count("This is one half of three.") == 3, (
        "not every evidence-writing mode says its half is one of three; "
        f"found {source.count('This is one half of three.')}"
    )


def test_the_gate_deploys_nothing(source: str) -> None:
    """A gate that deploys cannot be re-run to confirm a fix (D20).

    `apg dev up` in step 8 is not a deploy and the distinction is the session's:
    it builds a disposable local cluster from the rendered document and the
    release, touches no host, no secret store and no provider, and `down`
    removes it. What is forbidden is what converges the DEPLOYMENT.
    """
    for forbidden in ("./deploy.sh --host", "project-runtime.sh", "materialize-secrets"):
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            assert forbidden not in stripped, f"the gate runs {forbidden!r}: {stripped}"


def test_the_gate_takes_no_flag_that_could_carry_a_credential(source: str) -> None:
    """Inherited, and re-asserted because a derivation is where one would arrive.

    The password file flags are the exception and are named: they declare a
    secret the host HOLDS, which the gate reads to obtain a session. A flag
    that let an operator TYPE a token would make the gate measure the token.
    """
    for forbidden in ("--agent-token", "--capability-lock"):
        assert f'die 2 "there is no {forbidden}' in source, (
            f"{forbidden} is no longer refused by name; a gate given one measures "
            "the credential somebody typed rather than the deployment"
        )
