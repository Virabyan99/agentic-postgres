"""The Session 23 gate: a generated artefact, checked current and compiled.

**Derived from `test_session_twenty_two_gate_modes.py` by diff**, which is the
module of this family that Session 22's gate brought with it. What is carried
over is the shape that generalises: a gate is executable in the index, answers
all three modes, refuses an unknown one, names its OWN session's claims rather
than an inherited one (D459), writes its offline half from the run that
selected everything, passes no deployed document for it, refuses a workstation
with no docker, and deploys nothing.

**What is new is what an offline claim about a GENERATED ARTEFACT needs, and it
is two steps in two different places.** Both could be dropped without any other
test noticing:

* `generate --check`, in step 6 beside the contract checks, asks whether the
  committed client is CURRENT. It belongs there and not with the typecheck,
  because a stale client is usually still perfectly valid TypeScript -- so a
  gate that only compiled would go green on an artefact nobody compared;
* step 8b builds the hash-locked toolchain image and RUNS the client in it.
  The compiler is the only total check a generator's output has, and the first
  emitted package passed every structural proof and did not compile (D1223).

**And the offline/host split is this session's own argument**, which is why
this module asserts it rather than deriving it. Two claims are declared
offline because they are about the artefact and its generator; two are not,
because a checkout cannot say what a deployment serves or which lock a running
plane loaded. A later session that folded the second pair in would be reporting
eight minutes of beta serving the wrong lock as green (D1152).

The source-reading tests read `bin/session-23-check.sh` as text, which is the
right instrument for a shell script's structure and the wrong one for its
behaviour -- so the argument tests below actually RUN it.
"""

from __future__ import annotations

import subprocess

import pytest

from agentic_postgres import REPO_ROOT
from agentic_postgres import evidence_claims as claims

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCRIPT = REPO_ROOT / "bin" / "session-23-check.sh"
SESSION_PREVIOUS = REPO_ROOT / "bin" / "session-22-check.sh"

SESSION = 23

#: The claims Session 23 introduced, by mode. Written out rather than derived
#: from `claims_for_mode`, which would be the mechanism checking itself and
#: would pass for every possible claim table (D260's second mutation).
#:
#: **The split across the two modes is the assertion**, not an accident of how
#: the session ran. `generated_client` and `generated_client_toolchain` are
#: about the artefact and its generator, and four committed files and a
#: container settle every one of their proofs. `generated_client_hash` and
#: `agent_lock_reported` are about a running deployment -- what surface it
#: serves to a caller, and which lock its plane loaded -- and no checkout can
#: answer either. A later session that moved one of the second pair into the
#: first would make this table disagree with `claims_for_mode`, which is
#: exactly the day somebody should have to think about it.
#:
#: `external` is absent and that is also an assertion: a generated client is a
#: file an adopter holds, and inventing an external claim to make the shape
#: symmetric is what ADR 0065 refuses.
SESSION_TWENTY_THREE_CLAIMS = {
    "offline": ("generated_client", "generated_client_toolchain"),
    "host": ("generated_client_hash", "agent_lock_reported"),
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
    bit, and a gate nobody can execute fails in a way that reads as a bad path.

    **The path is derived from `SCRIPT`, not written out** (D1280, repaired in
    Session 25 Run 5). This module was derived from Session 22's and carried
    that module's own filename across, so it asserted the PREVIOUS gate's mode
    bit -- and a Session 23 gate committed without one would have passed it.
    Session 24's copy was written derived; this is the same repair, one module
    back.
    """
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", str(SCRIPT.relative_to(REPO_ROOT))],
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
    # **`code(source)`, not `source`** (D1350). The gate's own header says
    # *`readonly SESSION=NN` is the only session literal*, so the raw text
    # carries the string whatever the assignment below it says -- and a battery
    # that set the assignment to the previous session's number left this GREEN.
    # D277 and D1197 are the same class, and the helper this line now uses was
    # written for them.
    assert f"readonly SESSION={SESSION}" in code(source), (
        f"the gate does not assign SESSION={SESSION}. Its header may still SAY so, "
        "which is why this reads the comment-stripped text"
    )

    # **Derived, because a literal here goes stale silently** (D1280, repaired
    # in Session 25 Run 5). This module looked for `session-21-check` -- the
    # gate BEFORE the one this gate was derived from -- so it has been passing
    # for free since the day it was written, which is the same defect as the
    # one the guard it contains exists to catch. Session 24's copy was written
    # derived; this is that repair applied one module back.
    previous = SESSION_PREVIOUS.name
    provenance = f"**Derived from bin/{previous} by diff, not retyped**"
    assert provenance in source, (
        f"the gate does not say which gate it was derived from: expected {provenance!r}"
    )
    stale = [
        line
        for line in source.splitlines()
        if previous.removesuffix(".sh") in line and provenance not in line
    ]
    assert not stale, (
        f"a Session {SESSION - 1} filename survived the derivation: {stale}. The gate "
        "would write the previous session's evidence while its --help named files it "
        "never writes"
    )


def test_the_previous_gate_still_names_its_own_session() -> None:
    """Deriving a gate must not edit the one it was derived from."""
    assert f"readonly SESSION={SESSION - 1}" in SESSION_PREVIOUS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The offline half -- `EVD-OFFLINE-001`
# ---------------------------------------------------------------------------


def test_offline_mode_writes_the_offline_half(source: str) -> None:
    """`EVD-OFFLINE-001`. The first offline mode in this project that writes one.

    Four properties, and each is a way this could be wrong while looking right.

    **It is written.** Every earlier gate's offline mode ends by printing
    PASSED, and a Session 23 gate that did the same would close a session whose
    two offline claims nothing had recorded.

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
        "offline mode writes no evidence half. Session 23's own offline claims are "
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


def test_offline_mode_checks_the_committed_client_is_current(source: str) -> None:
    """`GEN-VERSION-001` in the gate. The drift check, and WHERE it sits.

    A generated artefact that is committed has one failure mode worth a gate:
    it stops being what the generator produces. `generate --check` is the whole
    of that question, and it belongs with the contract checks in step 6 rather
    than with the typecheck in step 8b -- because **a stale client is usually
    still perfectly valid TypeScript**, so a gate that only compiled would go
    green on an artefact nobody had compared.

    The ORDER is what is asserted, not merely the presence: the check runs
    before the image is built, so an operator who has forgotten to regenerate
    learns it in a fifth of a second rather than after a docker build.

    Found as a command in the comment-stripped text (D1197): this gate explains
    at length what each step does, and its own comment beside this line
    contains the words `generate --check`.

    Goes red if: the check is dropped; it moves after the typecheck; or it
    stops naming the project, in which case it would check the release's client
    -- a different artefact, which is not committed.
    """
    offline_mode = body_of(source, "mode_offline")
    lines = offline_mode.splitlines()
    checks = [
        index
        for index, line in enumerate(lines)
        if line.strip().startswith("bin/apg.sh generate --check")
    ]
    assert checks, (
        "offline mode does not run `generate --check`. The committed example "
        "client could then be anything, and the typecheck below would pass on it"
    )
    assert "project.example.yaml" in lines[checks[0]], (
        "the drift check names no project, so it checks the release's client -- "
        "which is a different artefact and is not committed"
    )

    builds = [index for index, line in enumerate(lines) if line.strip().startswith("docker build")]
    assert builds and checks[0] < builds[0], (
        "the client is typechecked before it is checked for drift. A stale client "
        "is usually still valid TypeScript, so the container would go green"
    )


def test_offline_mode_compiles_and_runs_the_generated_client(source: str) -> None:
    """`GEN-TOOLCHAIN-001` in the gate. Step 8b, and why it RUNS the package.

    **The compiler is the only total check a generator's output has**, and not
    running it declines it: the first emitted package satisfied eight green
    structural proofs and did not compile (D1223). The second typechecked at
    exit 0 and could not be executed at all, because its import specifiers
    named `.js` files a package that is never compiled does not have (D1226).
    So the step compiles AND runs, and both halves are asserted here.

    The base image is passed explicitly. An image built without it carries
    whatever `node:22-alpine` resolves to on the day, and the whole point of a
    hash-locked toolchain is that the compiler is the one `versions.env`
    records.

    The client is mounted READ-ONLY. A typecheck that could write into the
    artefact it is checking is a typecheck that can make itself pass.

    Goes red if: the step is dropped; the image stops being built from this
    checkout; `BASE_IMAGE` stops being passed; the mount loses `:ro`; or the
    run stops asking for the smoke, leaving a package that compiles and has
    never been executed.
    """
    offline_mode = body_of(source, "mode_offline")
    assert 'step "8b.' in offline_mode, "there is no step 8b"

    step = offline_mode[offline_mode.index('step "8b.') :]
    step = step[: step.index('step "9.')] if 'step "9.' in step else step

    assert "docker build" in step and "services/clients/typescript" in step, (
        "step 8b does not build the toolchain image from its own directory"
    )
    assert "BASE_IMAGE=" in step, (
        "the image is built without the pinned base, so the compiler in it is "
        "whatever the day's `node:22-alpine` carries"
    )
    assert "versions.env" in step, "the base image is not read from the lock"
    assert "projects/example/clients/typescript:/work:ro" in step, (
        "the committed client is not mounted read-only; a typecheck that can write "
        "into what it checks can make itself pass"
    )


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
    assert "--offline-input evidence/session-23-offline.json" in result.stdout, (
        "the merge command omits the offline half. `merge` REQUIRES it exactly "
        "when the session has offline claims, so the documented command would "
        "exit 2 for the operator who copied it"
    )
    assert "--host-input evidence/session-23-host.json" in result.stdout
    assert "--external-input evidence/session-23-external.json" in result.stdout
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
    for mode, expected in SESSION_TWENTY_THREE_CLAIMS.items():
        resolved = set(claims.claims_for_mode(mode, SESSION))
        missing = sorted(set(expected) - resolved)
        assert not missing, (
            f"{mode} mode does not carry Session 23's own claims {missing}. The "
            "gate would write a half that is silent about them, and the merge "
            "would refuse"
        )


def test_the_expectation_table_names_every_claim_this_session_introduced() -> None:
    """**Guard the guard.** Otherwise a row can be deleted to make the test pass.

    The same hole `test_every_claim_is_declared_here` closes for
    `CLAIM_INTRODUCED_IN`, closed the same way: the table and the claim set have
    to name the same things.
    """
    declared = {claim for group in SESSION_TWENTY_THREE_CLAIMS.values() for claim in group}
    introduced = {claim for claim in claims.CLAIMS if claims.claim_session(claim) == SESSION}
    assert declared == introduced, (
        "the expectation table and the claims introduced in this session "
        f"disagree: only in the table {sorted(declared - introduced)}, "
        f"only in CLAIMS {sorted(introduced - declared)}"
    )


def test_every_session_twenty_three_claim_belongs_to_session_twenty_three() -> None:
    """ADR 0089. A claim built from an earlier session's id moves, silently.

    `claim_session` is a `max()`, so one older requirement id mixed into a
    Session 23 claim either drags it into an earlier gate's evidence -- turning
    that session's document red -- or hides it from this one entirely. D1150 is
    the live instance: the plan had two Session 21 requirements joining Session
    16 and Session 18 claims, and the guard caught it on the first run.
    """
    for expected in SESSION_TWENTY_THREE_CLAIMS.values():
        for claim in expected:
            assert claims.claim_session(claim) == SESSION, (
                f"{claim} resolves to session {claims.claim_session(claim)}, not {SESSION}"
            )


def test_exactly_the_six_declared_claims_are_offline() -> None:
    """The declaration is the whole definition (ADR 0202), so it is asserted.

    **Session 22's version of this test asserted an EQUALITY against the whole
    of `OFFLINE_CLAIMS`**, which was right while that session's four were all
    there were, and became a rule that no later session may declare an offline
    claim the moment this one did. It failed on the second offline session --
    which is the earliest it could have, and late enough that the assertion had
    read as correct for a whole session (D1237).

    So the property is stated at the level it is actually about. This session
    owns two names and asserts them exactly, by SUBTRACTION: `OFFLINE_CLAIMS`
    less every claim an earlier session introduced must be precisely the two
    this session declared -- neither fewer nor a third that arrived without
    anybody deciding to, which is the failure the declaration exists to
    prevent. The earlier sessions' own names are checked by their own modules,
    where they belong.
    """
    from tests.contract.test_evidence_claims import CLAIM_INTRODUCED_IN

    # **Matched on THIS session, not subtracted from the earlier ones** (D1281).
    # The subtraction was right while this was the newest offline session and
    # became "no later session may declare one" the moment there was a later
    # one -- which is D1237's own defect, one turn on.
    mine = {name for name in claims.OFFLINE_CLAIMS if CLAIM_INTRODUCED_IN.get(name) == SESSION}
    assert mine == set(SESSION_TWENTY_THREE_CLAIMS["offline"]), (
        "the offline claims this session introduced and the ones it declared "
        f"disagree: {sorted(mine ^ set(SESSION_TWENTY_THREE_CLAIMS['offline']))}"
    )

    # And none of this session's HOST claims drifted into the declaration. That
    # is the direction with a consequence: a host claim declared offline goes
    # green on a checkout that never saw the deployment it is about.
    for claim in SESSION_TWENTY_THREE_CLAIMS["host"]:
        assert claim not in claims.OFFLINE_CLAIMS, (
            f"{claim} is declared offline. It is about a running deployment -- what "
            "surface it serves a caller, or which lock its plane loaded -- and a "
            "checkout answering it would report eight minutes of beta serving the "
            "wrong lock as green (D1152)"
        )
    for claim in SESSION_TWENTY_THREE_CLAIMS["host"]:
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
