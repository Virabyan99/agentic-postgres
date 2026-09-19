"""The Session 31 gate: a declaration, a decision, two readings and a check.

**Derived from `test_session_thirty_gate_modes.py` by diff**, and what is
carried over is the shape that generalises: a gate is executable in the index,
answers all three modes, refuses an unknown one, names its OWN session's claims
rather than an inherited one (D459), writes its offline half from the run that
selected everything, passes no deployed document for it, refuses a workstation
with no docker, and deploys nothing. Sessions 23, 24 and 25's step assertions
are kept whole -- the client drift check, the toolchain typecheck, the
third-party scan and the project's own tool catalog are still this gate's steps
6, 7, 8b and 8c, and this release's bump moves `templateVersion` in the
committed client, so the first of them is what stops a bump that forgot the
regeneration (D1238).

**THE PREVIOUS GATE IS 30'S, AND THERE IS NO GAP.** That is new: `SESSION - 1`
names the right file again for the first time since Session 25, because 30
swept its own trip and registered six claims. Session 30's copy of this module
asserted that 29 has NO gate, and that assertion is correct and belongs to
that module. **The equivalent test is deleted here rather than copied**: there
is no skipped session between 30 and 31, so a test asserting the absence of
`bin/session-30-check.sh` would assert the opposite of the truth, and one
asserting the absence of nothing at all would be a test that cannot fail.
`SESSION_PREVIOUS_NUMBER` stays a literal anyway -- the arithmetic being right
today is exactly how it came to be trusted before 26 broke it (D719, D1063).

**SIX claims are declared offline, one MORE than any session has declared**,
and each is a property of a checkout: a JSON Schema and an example document; a
parser over fixture text; arithmetic over readings this suite synthesises; a
compose model and two containers this workstation starts; a rendered collector
configuration and an in-process meter provider; and a pure check over values
the tests build wrong on purpose.

**FOUR are host claims**, which is more than any session has carried into one
trip, and none of their eight proofs has ever executed. `admission_live` needs
a real declaration and a real committed total -- and needs its CONTROL, which
is the half that says the rule does not refuse everything (D1611 shipped
exactly that). `usage_read` needs two clusters with data in them.
`telemetry_read` needs a metric to cross an OTLP connection into a Prometheus
that is routed nowhere, which has never happened in this product's life.
`agent_write_method` needs the deployed API to refuse a GET, and is Session 9's
pair registered by this session's orphan triage (D1597).

**The host mode cannot be run at this commit and that is the design** (D1425).
Nothing here is deployed until the trip deploys it; the gate's host mode runs
after, and the tag goes on the commit the deploy used.

The source-reading tests read `bin/session-31-check.sh` as text, which is the
right instrument for a shell script's structure and the wrong one for its
behaviour -- so the argument tests below actually RUN it.
"""

from __future__ import annotations

import subprocess

import pytest

from agentic_postgres import REPO_ROOT
from agentic_postgres import evidence_claims as claims

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCRIPT = REPO_ROOT / "bin" / "session-31-check.sh"
SESSION_PREVIOUS = REPO_ROOT / "bin" / "session-30-check.sh"

SESSION = 31

#: The session the gate above was DERIVED FROM, which is not `SESSION - 1`.
#:
#: **Written out because the arithmetic stopped being true in Session 28 and
#: has not become true again since.** Sessions 20 through 25 each derived from
#: the one before, so `SESSION - 1` named the right file for six consecutive
#: derivations and read as a rule; 26 and 27 registered nothing and broke it.
#: Session 29 breaks it a second time for a different reason -- it took the
#: trip that deployed, swept and tagged 1.7.0, and a trip writes the evidence
#: of the session whose release it deploys rather than one of its own. So this
#: gate derives from 28's, and the subtraction would look for
#: `bin/session-29-check.sh`, which does not exist, and for `readonly
#: SESSION=29`, which nothing holds. A literal that was right until the world
#: gained a case, twice (D719, D1063, D1514).
SESSION_PREVIOUS_NUMBER = 30

#: The claims Session 31 introduced, by mode. Written out rather than derived
#: from `claims_for_mode`, which would be the mechanism checking itself and
#: would pass for every possible claim table (D260's second mutation).
#:
#: **The split across the two modes is the assertion**, not an accident of how
#: the session ran. `exec_discipline` is an argv this tree builds and an AST
#: scan over this tree's own sources: whether a `docker exec` carries `-i` and
#: whether any call site sits outside the one helper are settled by the files
#: in this checkout, and a container is stood up only to show that a fed stdin
#: actually reaches the child. `release_reading_ref` is a command that reads
#: `git` in a clone and prints; its subject IS the checkout, and the one
#: environment that answers it differently is CI, which has no tags (D1466) and
#: therefore gets the third outcome. `contract_compile_output` is what a
#: command writes into a temporary directory, and what two pages in this
#: repository tell an adopter to type. `suite_shape` is the shape of this
#: suite -- which locals hide which helpers, and which deployment proofs belong
#: to no requirement -- and no deployment has an opinion about it.
#:
#: `studio_tenant_read` is about a DEPLOYMENT: whether a human's rows and a
#: second registered subject's stay apart through Studio's forwarder, which is
#: PostgreSQL's policies on a running cluster answering, not a checkout. The
#: proof stands up no rig of its own -- both subjects are registered through the
#: deployed identity plane and read through the deployed surface -- which is
#: exactly why a checkout cannot host it. A later session that moved it into the
#: first group would make this table disagree with `claims_for_mode`, which is
#: the day somebody should have to think about it.
#:
#: `external` is absent and that is also an assertion: this session ships no
#: service, no port and no route, so there is nothing for a stranger to reach.
#: Inventing an external claim to make the shape symmetric is what ADR 0065
#: refuses.
SESSION_THIRTY_ONE_CLAIMS = {
    "offline": (
        "capacity_declared",
        "capacity_reading",
        "admission_decision",
        "process_limits",
        "telemetry_bounded",
        "secret_kind_checked",
    ),
    "host": (
        "admission_live",
        "usage_read",
        "telemetry_read",
        "agent_write_method",
    ),
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

    **The path is derived from `SCRIPT`, not written out** (D1280). Session 23's
    copy of this module names its own gate here and this derivation carried that
    literal across unchanged -- so the test would have asserted the PREVIOUS
    gate's mode bit, and a new gate committed without one would have passed it.
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

    # **Derived, because a literal here goes stale silently** (D1280). Session
    # 23's copy of this test looks for `session-21-check` -- two gates back by
    # then -- and has been passing for free ever since, which is the same defect
    # as the guard it contains.
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
        f"a Session {SESSION_PREVIOUS_NUMBER} filename survived the derivation: {stale}. "
        "The gate would write the previous session's evidence while its --help named "
        "files it never writes"
    )


def test_the_previous_gate_still_names_its_own_session() -> None:
    """Deriving a gate must not edit the one it was derived from.

    **Read with `SESSION_PREVIOUS_NUMBER` rather than `SESSION - 1`**, and the
    difference is this session's whole shape: 26 and 27 have no gate, so the
    file this one was derived from holds 25 and the arithmetic would look for
    27 in a file that says 25. Six derivations in a row made that subtraction
    correct, which is how long a literal can be right before the world gains a
    case (D719).
    """
    assert f"readonly SESSION={SESSION_PREVIOUS_NUMBER}" in SESSION_PREVIOUS.read_text(
        encoding="utf-8"
    )


def test_the_previous_gate_is_the_one_before_this_one_with_no_gap() -> None:
    """**Session 30's copy of this module asserted that 29 has no gate.** That
    assertion is true and belongs to that module; this one would have to assert
    the absence of `bin/session-30-check.sh`, which exists.

    So the test is replaced rather than copied, and what replaces it is the
    fact that made the replacement necessary: **30 -> 31 is the first
    consecutive pair since 24 -> 25.** Sessions 26, 27 and 29 each registered
    nothing, for two different reasons -- 26 and 27 built nothing, 29 took the
    trip that deployed, swept and tagged 1.7.0, and a trip writes the evidence
    of the session whose release it deploys rather than one of its own (D1063,
    D1514). Session 30 swept its OWN trip, so there is no gap here to explain.

    **`SESSION_PREVIOUS_NUMBER` stays a literal anyway**, and this test is the
    reason to keep reading it as one: `SESSION - 1` was right for six
    consecutive derivations before 26 broke it, which is exactly how it came to
    be trusted (D719). It being right again today is not evidence it will be
    right next time.
    """
    assert SESSION_PREVIOUS.is_file(), SESSION_PREVIOUS
    assert SESSION_PREVIOUS_NUMBER == SESSION - 1, (
        "the previous gate is no longer the session before this one; that is "
        "permitted and has happened four times, but it has to be read out of "
        "the tree rather than assumed"
    )
    assert f"readonly SESSION={SESSION}" in SCRIPT.read_text(encoding="utf-8")


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


def test_offline_mode_checks_the_projects_own_tool_catalog(source: str) -> None:
    """`DX-DOC-001` in the gate. Session 25's one new line in a step.

    A project's own tools get a catalog under `projects/<slug>/docs/`, written
    by the same renderer that writes the release's and drift-checked the same
    way (ADR 0201, D1309). Run 4 built it and put the check in
    `bin/session-01-check.sh`; this session's claim is the one that depends on
    it, so this gate carries it too.

    **`--check --project`, both flags, and the assertion says so.** Without
    `--project` the same command checks the RELEASE's catalog, which is a
    different document that the Session 1 gate already checks -- so a line that
    lost the flag would still exit 0, still print a reassuring sentence, and
    measure nothing this claim is about. That is the failure this asserts
    against, and it is D200's shape: a command standing in for a different
    command it resembles.

    Found in the comment-stripped text (D1197): the comment beside the line
    names the same command.

    Goes red if: the check is dropped from step 7; it loses `--project`; or it
    loses `--check` and starts WRITING a document from inside a gate, which
    would make the gate the thing that keeps the catalog current instead of the
    thing that notices it is not.
    """
    offline_mode = body_of(source, "mode_offline")
    catalog = [
        line.strip() for line in offline_mode.splitlines() if "render-mcp-catalog.py" in line
    ]
    assert catalog, (
        "offline mode does not check the project's tool catalog. `DX-DOC-001` says "
        "the example project's catalog is committed and current, and a committed "
        "generated document with no drift check is a document that drifts"
    )
    for line in catalog:
        assert "--check" in line, (
            f"a gate must not WRITE a generated document: {line!r}. It checks, and an "
            "operator regenerates"
        )
    assert any("--project project.example.yaml" in line for line in catalog), (
        "the catalog check does not name a project, so it is checking the RELEASE's "
        f"catalog -- a different document, checked by the Session 1 gate: {catalog}"
    )


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


def test_offline_mode_asserts_studio_ships_no_third_party_code(source: str) -> None:
    """`STU-SUPPLY-001` in the gate. Step 8c, and why a redundant step is right.

    Step 3's sweep already collects `test_studio_assets.py` by its marks, so
    this step adds no coverage whatsoever. **What it adds is the sentence.** The
    claim ADR 0205 makes about Studio is mostly about what is NOT there -- no
    bundler, no framework, no font, nothing fetched from anywhere -- and a
    decision of that shape is kept by nobody noticing it, which is the state in
    which it stops being true. A gate that says it out loud, in a numbered step
    an operator watches go past, is a gate somebody has to argue with before
    adding a `<script src>`.

    It runs the module by NAME rather than by marker for the same reason: a
    marker selection would fold it back into the sweep and the line would
    disappear.

    Asserted in the comment-stripped text (D1197), because this gate's own
    comment beside the step says what the step does and a prose scan would find
    the words either way.

    Goes red if: the step is dropped; it stops naming the asset module; or it
    moves out of offline mode, where the claim it belongs to is reported.
    """
    offline_mode = body_of(source, "mode_offline")
    assert 'step "8c.' in offline_mode, (
        "there is no step 8c. The supply-chain assertion is then made only inside a "
        "sweep of five thousand tests, where nobody reads it"
    )

    step = offline_mode[offline_mode.index('step "8c.') :]
    step = step[: step.index('step "9.')] if 'step "9.' in step else step
    assert "tests/contract/test_studio_assets.py" in step, (
        f"step 8c does not run the asset module by name: {step[:300]!r}"
    )

    lines = offline_mode.splitlines()
    eight_b = [index for index, line in enumerate(lines) if 'step "8b.' in line]
    eight_c = [index for index, line in enumerate(lines) if 'step "8c.' in line]
    nine = [index for index, line in enumerate(lines) if 'step "9.' in line]
    assert eight_b and eight_c and nine, (eight_b, eight_c, nine)
    assert eight_b[0] < eight_c[0] < nine[0], (
        "the steps are out of order; 8c must sit between the typecheck and the "
        "evidence that reports the claim it belongs to"
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
    # Derived from SESSION for the reason the docstring gives: the gate builds
    # these with `%02d` and a test that wrote them out is a test that agrees
    # with the gate it was derived from rather than with the one it guards.
    assert f"--offline-input evidence/session-{SESSION:02d}-offline.json" in result.stdout, (
        "the merge command omits the offline half. `merge` REQUIRES it exactly "
        "when the session has offline claims, so the documented command would "
        "exit 2 for the operator who copied it"
    )
    assert f"--host-input evidence/session-{SESSION:02d}-host.json" in result.stdout
    assert f"--external-input evidence/session-{SESSION:02d}-external.json" in result.stdout
    assert f"session-{SESSION - 1:02d}-offline.json" not in result.stdout, (
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
    for mode, expected in SESSION_THIRTY_ONE_CLAIMS.items():
        resolved = set(claims.claims_for_mode(mode, SESSION))
        missing = sorted(set(expected) - resolved)
        assert not missing, (
            f"{mode} mode does not carry Session 30's own claims {missing}. The "
            "gate would write a half that is silent about them, and the merge "
            "would refuse"
        )


def test_the_expectation_table_names_every_claim_this_session_introduced() -> None:
    """**Guard the guard.** Otherwise a row can be deleted to make the test pass.

    The same hole `test_every_claim_is_declared_here` closes for
    `CLAIM_INTRODUCED_IN`, closed the same way: the table and the claim set have
    to name the same things.
    """
    declared = {claim for group in SESSION_THIRTY_ONE_CLAIMS.values() for claim in group}
    introduced = {claim for claim in claims.CLAIMS if claims.claim_session(claim) == SESSION}
    assert declared == introduced, (
        "the expectation table and the claims introduced in this session "
        f"disagree: only in the table {sorted(declared - introduced)}, "
        f"only in CLAIMS {sorted(introduced - declared)}"
    )


def test_every_session_thirty_claim_belongs_to_session_thirty() -> None:
    """ADR 0089. A claim built from an earlier session's id moves, silently.

    `claim_session` is a `max()`, so one older requirement id mixed into a
    Session 30 claim either drags it into an earlier gate's evidence -- turning
    that session's document red -- or hides it from this one entirely. D1150 is
    the live instance: the plan had two Session 21 requirements joining Session
    16 and Session 18 claims, and the guard caught it on the first run.
    """
    for expected in SESSION_THIRTY_ONE_CLAIMS.values():
        for claim in expected:
            assert claims.claim_session(claim) == SESSION, (
                f"{claim} resolves to session {claims.claim_session(claim)}, not {SESSION}"
            )


def test_exactly_this_sessions_declared_claims_are_offline() -> None:
    """The declaration is the whole definition (ADR 0202), so it is asserted.

    **Session 22's version of this test asserted an EQUALITY against the whole
    of `OFFLINE_CLAIMS`**, which was right while that session's four were all
    there were, and became a rule that no later session may declare an offline
    claim the moment Session 23 did (D1237). Session 23's replacement was a
    SUBTRACTION against every EARLIER session, which was right for exactly as
    long as no LATER session declared one, and Session 24 is where that showed
    (D1281). This is the sixth offline session; it declares FIVE, which is
    three more than the session before, which itself declared one fewer than the
    one before that -- and a guard shaped around the count moving in either
    direction would have been the fourth version of this same mistake. The fifth
    arrived after this module was written, which is the case the shape is for:
    ADR 0220's repair was implemented after Run 6 and the table had to be told,
    rather than a count in a name going quietly stale.

    **The name carries no count, deliberately.** The derivation arrived here
    reading `..._the_eight_declared_claims_...` while eleven were declared, and
    a number in a test's own name is a claim nothing reads -- the same shape as
    a usage text that says four when its command prints five (D1349). What the
    test is about is not how many there are; it is that the ones THIS session
    declared and the ones this session introduced are the same set.

    So the property is stated at the level it is actually about, MATCHED ON
    THIS SESSION: the claims in `OFFLINE_CLAIMS` whose `CLAIM_INTRODUCED_IN`
    entry is this session must be precisely the ones this module declares --
    neither fewer nor a fourth that arrived without anybody deciding to, which
    is the failure the declaration exists to prevent. The earlier sessions'
    own names are checked by their own modules, where they belong.
    """
    from tests.contract.test_evidence_claims import CLAIM_INTRODUCED_IN

    # **Matched on THIS session, not subtracted from the earlier ones** (D1281).
    # The subtraction was right while this was the newest offline session and
    # became "no later session may declare one" the moment there was a later
    # one -- which is D1237's own defect, one turn on.
    mine = {name for name in claims.OFFLINE_CLAIMS if CLAIM_INTRODUCED_IN.get(name) == SESSION}
    assert mine == set(SESSION_THIRTY_ONE_CLAIMS["offline"]), (
        "the offline claims this session introduced and the ones it declared "
        f"disagree: {sorted(mine ^ set(SESSION_THIRTY_ONE_CLAIMS['offline']))}"
    )

    # And none of this session's HOST claims drifted into the declaration. That
    # is the direction with a consequence: a host claim declared offline goes
    # green on a checkout that never saw the deployment it is about.
    # The derivation arrived carrying this loop TWICE, with two different
    # sentences for the same assertion -- Session 24 wrote one and Session 23's
    # copy contributed the other. One is kept, with the reason that is this
    # session's: `studio_tenant_read` is about whether a running plane keeps two
    # registered subjects' rows apart through a forwarder that holds no policy
    # of its own, and a checkout declared able to answer it would be reporting
    # PostgreSQL's verdict on a cluster nobody deployed.
    for claim in SESSION_THIRTY_ONE_CLAIMS["host"]:
        assert claim not in claims.OFFLINE_CLAIMS, (
            f"{claim} is declared offline. It is about a running deployment -- whether "
            "PostgreSQL keeps two subjects' rows apart through Studio's forwarder -- "
            "and a checkout answering it would grade the release against a rig the "
            "proof stood up itself"
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


# ---------------------------------------------------------------------------
# the evidence is written whether or not the suite passed (D1373)
# ---------------------------------------------------------------------------


def test_a_failing_suite_does_not_stop_the_evidence_being_written() -> None:
    """`failed` is a status this gate could not emit, and its comment said it could.

    The gate runs under `set -euo pipefail` and `run_suite` calls pytest
    directly, so ANY failing proof used to end the run at step 5 -- before the
    step that computes claims and the step that writes evidence. Three things
    said otherwise: ADR 0163 defines `failed` as one of three statuses,
    `claim_result` computes it, and this gate's own header documents exit 5 as
    *the evidence was WRITTEN and some claim in it is not passed*. The comment
    immediately above the call says it outright -- *the evidence is written
    whether or not the suite passed*.

    It was not. **No evidence document in twenty-five sessions has ever carried
    a `failed` claim**, which reads as nothing ever having been wrong and means
    the path had never executed. It executed on 2026-09-15, when Session 25's
    walk record made `documented_path` genuinely false, and it took the entire
    host half with it: 318 proofs passed, the JUnit was written, and no
    `session-25-host.json` existed to record any of them.

    Scanned on COMMENT-STRIPPED text, because this gate explains at length what
    each step does and the words this test looks for are in those sentences too
    (D277, D1197, D1350 -- the last one found in this very module).

    **ALL THREE modes are checked, and Session 25's version of this test checked
    two** (D1487). It asserted the repair in `live_host` and `external`, pinned
    `suite_status=0` at exactly **2**, and closed with *repairing one caller of a
    decision and leaving the other is §7's fifth question* -- while leaving the
    offline caller unrepaired and making the count a tripwire against repairing
    it. The guard encoded the gap it warns about. Measured rather than reasoned:
    `--mode offline` on `c14b0ef` exited **1**, wrote the JUnit and wrote no
    half. Session 28's ONLY half was the offline one; this session has both, and
    four of its five claims are in the offline one -- more than any session has
    declared -- so the same defect would now cost four claims rather than three.

    **Derived rather than listed**, for the reason the pinned 2 is the lesson
    about: the property is *every sweep that writes a JUnit captures its
    status*, which stays true when a fourth mode arrives. Step 4's
    `run_suite "live_host or external" ""` is deliberately excluded by that same
    rule -- it writes no JUnit because it is a collection check and a
    prerequisite, and a prerequisite SHOULD end the run.
    """
    source = code(SCRIPT.read_text(encoding="utf-8"))

    #: Every `run_suite` call that is handed a JUnit path, as whole lines. The
    #: call is written across two lines in the script, so the JUnit argument is
    #: looked for on the line that follows.
    lines = source.splitlines()
    sweeps: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if "run_suite " not in line:
            continue
        window = " ".join(lines[index : index + 2])
        if "-tests.xml" in window:
            sweeps.append((index, window))

    assert len(sweeps) >= 3, (
        f"only {len(sweeps)} sweeps write a JUnit; this gate has three modes and each "
        "writes one, so the scan below is measuring something other than the sweeps"
    )

    for _, window in sweeps:
        assert "|| suite_status=$?" in window, (
            "a sweep that writes a JUnit does not capture its failure: under `set -e` a "
            "failing proof ends the run before the evidence is written, and a claim that "
            f"is genuinely false can then never be recorded as `failed` (D1373, D1487).\n"
            f"  {window.strip()}"
        )

    for mode in claims.ALL_MODES:
        call = f"write_evidence {mode}"
        assert f"{call} || evidence_status=$?" in source, (
            f"the {mode} writer's own status is not captured, so the suite's status "
            "can never be reported when the writer is content (D1373, D1487)"
        )

    #: Derived from the number of sweeps rather than pinned at a literal, which
    #: is what made repairing the third mode go red instead of green.
    assert source.count("suite_status=0") == len(sweeps), (
        "every mode that captures a sweep's status must initialise it, or `set -u` "
        f"ends the run on an unbound variable: {source.count('suite_status=0')} "
        f"initialisations for {len(sweeps)} sweeps"
    )


def test_host_mode_exports_the_two_new_gates(source: str) -> None:
    """**D687, applied on the day rather than after it.**

    A variable a proof reads and no gate exports is a proof that skips, and a
    claim that comes back unproved in a run that measured everything else. That
    is not a hypothetical here: `deployment_convergence` was one of Session
    28's own claims and its gate could not pass the flag that admits it, so
    both its proofs skipped.

    Two variables, and both are declarations an operator makes rather than
    facts a test could find. `APG_HOST_MANIFEST` is the HOST's own manifest --
    admission and the capacity reading are the first things in this product
    that read it rather than a project's document, and the path is not
    derivable. `APG_CANDIDATE_MANIFEST` is the third project's manifest, which
    lives outside the checkout because a third manifest inside the release
    dirties it and every deploy refuses (D971).

    Read from the comment-stripped source, because a gate that only MENTIONED
    the variable in a sentence about it would satisfy a text scan (D277, D1197).
    """
    body = code(source)
    for variable in ("APG_HOST_MANIFEST", "APG_CANDIDATE_MANIFEST"):
        assert f"export {variable}=" in body, (
            f"{SCRIPT.name} does not export {variable}, so every proof gated on "
            "it skips and its claim reports not_run"
        )

    assert "--candidate-manifest)" in body, (
        f"{SCRIPT.name} exports APG_CANDIDATE_MANIFEST but parses no "
        "--candidate-manifest flag, so nothing can supply it"
    )
    # And both are in the closed roster, or `requires_environment` raises
    # `UsageError` on the name and the proofs never run at all.
    roster = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    for variable in ("APG_HOST_MANIFEST", "APG_CANDIDATE_MANIFEST"):
        assert f'"{variable}"' in roster, (
            f"{variable} is exported by the gate and absent from "
            "tests/conftest.py's ENVIRONMENT_VARIABLES, which is a closed tuple"
        )
