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

**The first rule was scoped to one file and the defect was not** (D719).
``bin/write-session-evidence.py`` held ``if not 1 <= args.session <= 12``, so the
first Stage 2 session could not write evidence -- refused by a bound that had
been correct at every previous check, because the number it named and the number
it meant coincided for twelve sessions. This module's rule was already the right
one; it named the gates and not the writer, which is question 5 exactly.

So the last section asserts the **class**: no operator command types the ceiling.
**A floor is not a ceiling and is deliberately allowed** -- ``< 1`` and ``< 2``
are facts about history that do not move, and ``bin/deploy-project.py`` carries
both shapes on one line: ``through_session < 2 or through_session >
CURRENT_SESSION``. Flagging the floor would make the guard wrong about the one
command that was already right.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

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


# ---------------------------------------------------------------------------
# The workflow is an operator command too (D871)
# ---------------------------------------------------------------------------

#: A session compared against ANY integer literal, rather than only against the
#: one `CURRENT_SESSION` happens to be today.
#:
#: `TYPES_THE_CURRENT_SESSION` above is deliberately narrower, and says so: it
#: "cannot catch a stale bound *after* the bump", because `<= 12` stops matching
#: once the constant is 13. In `bin/` that is acceptable, because the
#: load-bearing guard there is a command actually executed against the number.
#:
#: **A workflow is not executed by anything this suite runs**, so nothing here
#: can catch its bound by running it. The only affordable guard is textual, and
#: the narrow version would have caught `== 2` for exactly one session and then
#: gone quiet for thirteen -- which is what happened.
#:
#: A floor is not exempted here as it is in `bin/`. Nothing in a workflow needs
#: to say "session >= 3": the workflow runs one tree at one commit, and every
#: number it could compare against is derivable from that tree.
#: The shell operators are here because the control demanded them. The first
#: draft carried only the Python and arithmetic spellings, and its own offender
#: list -- ``if [ "${SESSION}" -gt 15 ]`` -- walked straight through it. A guard
#: over a workflow that reads only Python comparisons would be reading the one
#: language the file is least likely to be written in.
_OPERATOR = r"(?:<=|>=|==|!=|<|>|-eq\b|-ne\b|-lt\b|-le\b|-gt\b|-ge\b)"

COMPARES_A_SESSION_TO_A_LITERAL = re.compile(
    rf"""
    (?:
        \w*session\w* [}}\)"'\s]* {_OPERATOR} \s* \d
      | \d \s* {_OPERATOR} [\s"'$\{{]* \w*session\w*
      | --session \s+ \d
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _workflows() -> list[Path]:
    return sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))


def test_no_workflow_compares_a_session_against_a_literal() -> None:
    """D871. CI asserted ``CURRENT_SESSION == 2`` for thirteen sessions.

    It sat under a comment explaining that the session must be derived rather
    than passed, in the job whose failure made the whole workflow red -- and the
    guard that exists for exactly this, ``TYPES_THE_CURRENT_SESSION``, reads
    ``bin/*.py`` and nothing else. Question 5, in the file that decides whether
    anybody finds out.

    Comment lines are scanned too, unlike in the ``bin/`` guard. A comment in
    ``bin/`` explains a command a reader can run; a comment in a workflow that
    names a session number is describing a step beside it, and the two going out
    of step is the defect rather than a documentation slip.
    """
    offenders: list[str] = []
    for path in _workflows():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if COMPARES_A_SESSION_TO_A_LITERAL.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}  {line.strip()[:90]}")

    assert not offenders, (
        "a workflow compares a session against a literal; it will be wrong at the "
        "next bump and nothing outside GitHub will notice:\n  " + "\n  ".join(offenders)
    )


def test_the_workflow_scan_reads_the_files_and_catches_what_it_is_for() -> None:
    """The control, and the reason it is three parts (D694, D509).

    A scan over an empty list passes for ever. A scan that matched the step as
    it is written today would make the repair unlandable. Both halves have to be
    exercised or this is a green test nobody has seen fail.
    """
    workflows = _workflows()
    assert workflows, "the scan reads no workflow; .github/workflows/*.yml is empty"
    assert any(path.name == "ci.yml" for path in workflows), (
        "the scan excludes the very workflow D871 was about"
    )

    # The defect, in the spelling it actually had and in three others.
    for offender in (
        "'from agentic_postgres import CURRENT_SESSION;"
        " assert CURRENT_SESSION == 2, CURRENT_SESSION'",
        'if [ "${SESSION}" -gt 15 ]; then',
        "  # valid while session <= 12",
        "assert 2 == CURRENT_SESSION",
        "run: bin/write-session-evidence.py --session 15",
    ):
        assert COMPARES_A_SESSION_TO_A_LITERAL.search(offender), f"the scan misses: {offender!r}"

    # And the shapes a repaired workflow legitimately carries.
    for allowed in (
        "PYTHONPATH=src python -c 'from agentic_postgres import CURRENT_SESSION as s; print(s)'",
        "run: bin/session-01-check.sh",
        "name: Session 2 offline contract",
        'python -m pytest -q -m "p0 and not future"',
    ):
        assert not COMPARES_A_SESSION_TO_A_LITERAL.search(allowed), f"the scan flags: {allowed!r}"


def test_the_future_marker_step_tolerates_an_empty_selection() -> None:
    """D871/D695. ``pytest -m future`` exits 5 when it selects nothing.

    There are no ``future`` placeholders left, so the informational step that
    lists them has returned 5 -- and failed its job -- since the last one was
    activated. D695 repaired the *test* that assumed a non-empty selection and
    left this step, which makes the same assumption, running the same command.

    The assertion is deliberately about the step tolerating **5 and nothing
    else**: a step written to swallow every code would report a suite that could
    not even collect as "no outstanding work", which is the failure that is
    worse than the red one.
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "-m future" in workflow, "CI no longer lists outstanding future work"

    step = workflow.split("Show outstanding future work", 1)[1]
    assert "-m future" in step, "the future-work step no longer runs the marker"
    assert re.search(r"^\s*5\)", step, re.MULTILINE), (
        "the future-work step does not tolerate pytest's exit 5, which D695 "
        "measured is what an empty marker selection returns"
    )
    assert re.search(r"exit \"?\$\{?status", step), (
        "the future-work step swallows every exit code, not only 5; a broken "
        "suite would report as no outstanding work"
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


# ---------------------------------------------------------------------------
# The class: no operator command types the current session (D719)
# ---------------------------------------------------------------------------

#: Commands that ARE one session's own artefact, and so legitimately name its
#: number. A `session-NN-check.sh` is the record of the release it gated, the
#: same reason D693 exempts session-numbered operator guides: a document about
#: session 9 rewritten to say 13 would stop being a record of anything.
PER_SESSION_ARTEFACT = re.compile(r"^session-\d\d-check\.(sh|py)$")

#: A session compared against the literal that `CURRENT_SESSION` currently is.
#:
#: **Scoped this narrowly on purpose, and the first draft was not.** It tried to
#: separate a *ceiling* from a *floor* by the operator, and got both directions
#: wrong on its first run: it missed `session > 12` and flagged the three
#: legitimate `session < 1` floors. There is no textual rule that separates
#: `through_session >= 3` -- a feature gate, meaning "session 3 added a step" --
#: from `session > 12`, a refusal. They are the same shape and different things.
#:
#: What IS exactly decidable is whether a command has today's session number
#: written in it, and that is the whole defect: the bound in
#: `write-session-evidence.py` was not wrong because it was a ceiling, it was
#: wrong because the number it named and the number it meant had coincided for
#: twelve sessions.
#:
#: **This is the cheap half.** It cannot catch a stale bound *after* the bump --
#: `<= 12` stops matching once CURRENT_SESSION is 13. The load-bearing guard is
#: `test_the_evidence_writer_accepts_the_session_this_release_is` below, which is
#: unconditional and cannot go quiet.
TYPES_THE_CURRENT_SESSION = re.compile(
    rf"""
    (?:
        \w*session\w* \s* (?:<=|>=|==|<|>) \s* {CURRENT_SESSION}(?!\d)
      | (?<!\d){CURRENT_SESSION} \s* (?:<=|>=|==|<|>) \s* \w*session\w*
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _operator_commands() -> list[Path]:
    return sorted(
        path
        for path in (REPO_ROOT / "bin").glob("*.py")
        if not PER_SESSION_ARTEFACT.match(path.name)
    )


def test_no_operator_command_types_the_current_session() -> None:
    """D719. A command that serves every session may not name the current one.

    `bin/write-session-evidence.py` refused `--session 13` because it held
    `if not 1 <= args.session <= 12`. **It had been right at every check for
    twelve sessions**, because the number it named and the number it meant were
    the same one -- which is why a bound that fails closed is not therefore safe.

    `bin/deploy-project.py` is the shape that passes and always did:
    `through_session < 2 or through_session > CURRENT_SESSION`, a floor that is
    a fact about history beside a ceiling that is derived.
    """
    offenders: list[str] = []
    for path in _operator_commands():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if TYPES_THE_CURRENT_SESSION.search(stripped):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}  {stripped[:80]}")

    assert not offenders, (
        f"these compare a session against the literal {CURRENT_SESSION}, which is what "
        "CURRENT_SESSION is today; derive it instead:\n  " + "\n  ".join(offenders)
    )


def test_the_scan_reads_the_commands_and_catches_what_it_is_for() -> None:
    """The control, in three parts, because each fails differently (D694).

    A scan reading nothing reports every command clean forever. A scan that
    matched the floors would be wrong about the three commands that carry one
    legitimately, and about `deploy-project`, which was already correct.
    """
    commands = _operator_commands()
    assert len(commands) > 20, f"the scan sees {len(commands)} commands; it is not reading bin/"
    assert any(path.name == "write-session-evidence.py" for path in commands), (
        "the scan excludes the very command D719 was about"
    )

    # It catches the defect as it was actually written, in every spelling.
    for offender in (
        f"if not 1 <= args.session <= {CURRENT_SESSION}:",
        f"if arguments.session > {CURRENT_SESSION}:",
        f"if {CURRENT_SESSION} < session:",
    ):
        assert TYPES_THE_CURRENT_SESSION.search(offender), f"the scan misses: {offender!r}"

    # It permits a historical floor, a feature gate, a derived ceiling, and a
    # literal that merely starts with the same digits.
    for allowed in (
        "if arguments.session < 1:",
        "if arguments.through_session >= 3:",
        "if arguments.through_session < 2 or arguments.through_session > CURRENT_SESSION:",
        "if not 1 <= args.session <= CURRENT_SESSION:",
        f"if session_bytes > {CURRENT_SESSION}00:",
    ):
        assert not TYPES_THE_CURRENT_SESSION.search(allowed), f"the scan flags: {allowed!r}"


@pytest.mark.parametrize("beyond", [1, 2, 87])
def test_the_evidence_writer_refuses_a_session_this_release_does_not_implement(
    beyond: int,
) -> None:
    """Parametrized on ``CURRENT_SESSION + n`` rather than on a literal.

    The discipline `test_deploy_command` already uses, for the same reason: a
    test naming 13 would pass today and be a second typed ceiling tomorrow.
    """
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "bin" / "write-session-evidence.py"),
            "--session",
            str(CURRENT_SESSION + beyond),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"between 1 and {CURRENT_SESSION}" in result.stderr, result.stderr


def test_the_evidence_writer_accepts_the_session_this_release_is() -> None:
    """The half that would have caught D719, and the one that cannot go quiet.

    Unlike the scan above, this is unconditional: it asks the command about the
    session the release actually is, so it stays true through every bump without
    naming a number. It gets past the bound and fails later on the artifacts it
    was not given; that it got past is all this asserts.
    """
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "bin" / "write-session-evidence.py"),
            "--session",
            str(CURRENT_SESSION),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "between 1 and" not in result.stderr, (
        f"the bound refused the session this release IS:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# The prose a gate says out loud (D703, D751)
# ---------------------------------------------------------------------------

#: Every per-session gate.
SESSION_GATES = sorted((REPO_ROOT / "bin").glob("session-[0-9][0-9]-check.sh"))

#: A session number an operator is told to TYPE: an evidence filename, a
#: `--session N`, or a `--through-session N`.
#:
#: Deliberately not "any mention of a session". A gate legitimately says *"Session
#: 10 releases no migration"* -- a fact about history that does not move. What it
#: must never do is hand an operator a command carrying another session's number,
#: and those have a shape: they are arguments and filenames.
TYPED_SESSION_NUMBER = re.compile(
    r"""
    (?:
        evidence/session-(\d\d)          # evidence/session-10.json
      | --session\s+(\d+)                # --session 10
      | --through-session\s+(\d+)        # --through-session 10
    )
    """,
    re.VERBOSE,
)


def _gate_session(path: Path) -> int:
    match = re.search(r"session-(\d\d)-check\.sh$", path.name)
    assert match, path
    return int(match.group(1))


@pytest.mark.parametrize("gate", SESSION_GATES, ids=lambda path: path.name)
def test_a_gate_hands_the_operator_no_other_sessions_number(gate: Path) -> None:
    """D703, and D751 is the same loss two derivations later.

    D703 found two lines a gate PRINTS still naming Session 10, and repaired
    them by hand. Deriving the Session 13 gate found the whole class again:
    around thirty stale references, including a merge example telling an
    operator to write **`evidence/session-10.json` from a Session 12 run**. An
    operator who copied it would have overwritten an earlier session's evidence
    with this one's, and both commands would have exited 0.

    **Care did not prevent it and will not.** So the numbers an operator is told
    to type are interpolated from `${SESSION}` rather than written, and this
    refuses a literal.

    Scoped to arguments and filenames on purpose. A gate saying *"Session 10
    releases no migration"* is stating a fact about history, and a guard that
    flagged it would be wrong about every gate that explains its inheritance.
    """
    session = _gate_session(gate)
    offenders: list[str] = []

    for number, line in enumerate(gate.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for match in TYPED_SESSION_NUMBER.finditer(stripped):
            found = next(group for group in match.groups() if group is not None)
            if int(found) != session:
                offenders.append(f"{gate.name}:{number}  {stripped[:88]}")

    assert not offenders, (
        f"this gate hands an operator session numbers that are not its own "
        f"({session}); interpolate ${{SESSION}} instead:\n  " + "\n  ".join(offenders)
    )


def test_the_prose_scan_can_tell_a_typed_number_from_a_historical_one() -> None:
    """The control, and it fails in both directions (D694, D746).

    A scan matching nothing would report every gate clean forever. A scan
    matching every mention would be wrong about the gates that explain what they
    inherited -- and would have to be weakened with exemptions, which is how a
    guard becomes a guard about its exemptions.
    """
    assert SESSION_GATES, "no session gates found; the scan is reading nothing"

    for typed in (
        "--host-input evidence/session-10-host.json",
        "python bin/write-session-evidence.py --session 10",
        "Use ./deploy.sh --through-session 10",
    ):
        assert TYPED_SESSION_NUMBER.search(typed), f"the scan misses a typed number: {typed!r}"

    for historical in (
        "# Session 10 releases NO migration -- Run 5 measured that",
        "backups are not enabled. Every Session 10 project needs one.",
        "inherited from Sessions 4-9 are measured from off-host",
        'printf "--session %s" "${SESSION}"',
    ):
        assert not TYPED_SESSION_NUMBER.search(historical), (
            f"the scan flags a historical statement: {historical!r}"
        )
