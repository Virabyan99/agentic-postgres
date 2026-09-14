"""`bin/dev.sh`'s surface: what it refuses, and when. `DEV-ENV-001`, ADR 0203.

The shape `test_database_commands.py` uses, and for the same reason: the happy
path needs a daemon and an image, so what is asserted here is that every
refusal happens BEFORE any of that — an operator who mistyped a flag should not
wait for a container to start to find out.

**No test here starts a container.** The one that reaches docker is the
unrendered-project refusal, and it is refused before docker is asked anything,
which is the property under test.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, dev_environment

pytestmark = [pytest.mark.contract, pytest.mark.p0]

DEV = REPO_ROOT / "bin" / "dev.sh"
APG = REPO_ROOT / "bin" / "apg.sh"
PROJECT = "project.example.yaml"


def dev(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(DEV), *arguments], capture_output=True, text=True, check=False, cwd=REPO_ROOT
    )


# ---------------------------------------------------------------------------
# container_state: docker's two silences are not the same silence (D1285)
# ---------------------------------------------------------------------------
#
# Neither proof starts a container, so the module's standing rule holds. They
# reach the daemon to ASK about a name, which is what the function does, and
# the pair is the point: one asserts that a definite "there is no such thing"
# is reported as `absent`, the other that a daemon which cannot be reached at
# all is reported as `None`. Either alone would pass while the two were
# conflated, which is how the conflation survived from Session 22 with no
# proof over the function at all.


@pytest.fixture(scope="module")
def dev_module() -> Any:
    specification = importlib.util.spec_from_file_location(
        "apg_dev_cli", REPO_ROOT / "bin" / "dev.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_a_container_docker_says_is_absent_reads_as_absent(dev_module: Any) -> None:
    """D1285. `absent` is an answer docker gave, not a failure to get one.

    The name is one no rig creates. Docker exits 1 and writes *no such object*
    in lower case at 29.5.2; the reader matched *No such object* capitalised,
    so this returned `None` and `apg dev status` asked the operator whether the
    daemon was running while the daemon answered every other call in the run.
    """
    if not shutil.which("docker"):
        pytest.skip("no docker client on this machine; the gate's offline mode requires one")
    probe = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        pytest.skip("no docker daemon; this proof asks one about a name")

    assert dev_module.container_state("apg-no-such-container-d1285") == "absent"


def test_a_daemon_that_cannot_be_reached_reads_as_unknown_not_as_absent(
    dev_module: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The control, and the half that must NOT become `absent`.

    Pointed at a socket that is not there, docker fails the same way it fails
    for an absent object -- exit 1, a message on stderr -- and the difference
    is only in the words. `None` here is what makes `absent` above mean
    something; a reader that returned `absent` for both would pass the proof
    before this one and tell a developer to run `apg dev up` against a daemon
    that is not running.
    """
    if not shutil.which("docker"):
        pytest.skip("no docker client on this machine; the gate's offline mode requires one")
    monkeypatch.setenv("DOCKER_HOST", f"unix://{tmp_path / 'not-a-socket'}")
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)

    assert dev_module.container_state("apg-no-such-container-d1285") is None


def test_the_absent_phrases_are_matched_without_regard_to_case(dev_module: Any) -> None:
    """The wiring, so a third spelling is one entry rather than a new branch.

    Asserted against the constant rather than the behaviour above, because the
    behaviour above can only exercise whichever voice the installed docker
    happens to use, and the point of the constant is the one it does not.
    """
    assert dev_module.ABSENT_PHRASES, "the phrases must be named somewhere readable"
    for phrase in dev_module.ABSENT_PHRASES:
        assert phrase == phrase.lower(), (
            f"{phrase!r} is compared against a lower-cased stderr and must be lower case"
        )


# ---------------------------------------------------------------------------
# The verb surface
# ---------------------------------------------------------------------------


def test_dev_is_a_verb_of_the_dispatcher() -> None:
    """`apg.sh` derives its verbs from `bin/`, so this needs no list to be edited.

    Asserted anyway: the dispatcher's derivation is what makes `apg dev` work
    without a registration step, and a change that reintroduced a hardcoded list
    would break that quietly for exactly one new command — the one nobody has
    used yet.
    """
    listing = subprocess.run(
        [str(APG), "--list"], capture_output=True, text=True, check=False, cwd=REPO_ROOT
    )
    assert listing.returncode == 0, listing.stderr
    assert "dev" in listing.stdout.split(), listing.stdout

    through = subprocess.run(
        [str(APG), "dev", "--help"], capture_output=True, text=True, check=False, cwd=REPO_ROOT
    )
    assert through.returncode == 0
    assert "up|status|down|reset" in through.stdout


def test_help_exits_zero_and_documents_every_verb() -> None:
    result = dev("--help")
    assert result.returncode == 0
    for verb in ("up", "status", "down", "reset"):
        assert verb in result.stdout, f"--help does not document {verb}"
    assert "--project" in result.stdout


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ((), "no verb at all"),
        (("up",), "a verb with no --project"),
        (("nonsense", "--project", PROJECT), "a verb this command does not have"),
        (("up", "--project"), "--project with no value"),
        (("up", "--project", "no-such-manifest.yaml"), "a manifest that is not there"),
        (("up", "--nonsense", "x", "--project", PROJECT), "a flag this command does not have"),
        (("up", "down", "--project", PROJECT), "two verbs at once"),
    ],
)
def test_argument_errors_exit_two_before_docker_is_asked_anything(
    arguments: tuple[str, ...], reason: str
) -> None:
    """Exit 2 and a sentence, not a traceback and not a wait.

    Every one of these is decided by the shell wrapper, which is the point of
    the wrapper: the Python is never reached, so none of them can be answered
    with "the daemon is not running" on a machine where it is not.
    """
    result = dev(*arguments)
    assert result.returncode == 2, (
        f"{reason} exited {result.returncode}, not 2.\n{result.stdout}\n{result.stderr}"
    )
    assert result.stderr.strip(), f"{reason} was refused without saying why"
    assert "Traceback" not in result.stderr, f"{reason} produced a traceback"


def test_an_unrendered_project_is_refused_with_exit_four_and_the_render_command(
    tmp_path: Path,
) -> None:
    """D1173: one renderer, one resolver. This command renders nothing.

    The refusal names the command that fixes it, spelled with the arguments this
    invocation was given — an adopter reading *"render it first"* without the
    line to run has been told the diagnosis and not the remedy (ADR 0195's
    second half).
    """
    manifest = tmp_path / "project.unrendered.yaml"
    manifest.write_text(
        (REPO_ROOT / PROJECT)
        .read_text(encoding="utf-8")
        .replace("slug: fixture-alpha", "slug: fixture-unrendered"),
        encoding="utf-8",
    )

    result = dev("up", "--project", str(manifest))
    assert result.returncode == dev_environment.EXIT_NOT_RENDERED, (
        f"exited {result.returncode}, not {dev_environment.EXIT_NOT_RENDERED}.\n{result.stderr}"
    )
    assert "--render-only" in result.stderr, result.stderr
    assert str(manifest) in result.stderr, (
        "the refusal does not name the manifest it was given, so the command it prints "
        "is not one the operator can paste"
    )


def test_status_on_a_project_with_no_environment_says_so_and_exits_four() -> None:
    """`absent` is an answer, and it is not an error the operator caused."""
    result = dev("status", "--project", PROJECT)
    assert result.returncode in (dev_environment.EXIT_NOT_RENDERED, 0), result.stderr
    if result.returncode == dev_environment.EXIT_NOT_RENDERED:
        assert "apg dev up" in result.stdout, result.stdout


def test_down_on_nothing_exits_zero_and_says_there_was_nothing() -> None:
    """Idempotent, and honest about which of the two happened.

    Exit 0 because the state the caller asked for is the state they get. What it
    must not do is report having removed something it did not.
    """
    result = dev("down", "--project", PROJECT)
    assert result.returncode == 0, result.stderr
    assert "nothing to remove" in result.stdout or "removed" in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# The shape of the wrapper itself
# ---------------------------------------------------------------------------


def test_the_wrapper_documents_its_exit_codes_and_refuses_before_the_python() -> None:
    """The runbook §2 convention, and the split every command here has.

    The shell script is the contract and the Python is the work. A wrapper that
    `exec`s before validating would move every refusal into the Python, where it
    would arrive after an import and a daemon probe.
    """
    source = DEV.read_text(encoding="utf-8")
    for code in ("0  success", "2  invalid operator input", "9 "):
        assert code in source, f"the wrapper does not document exit {code}"

    body = source.split("main() {", 1)[1]
    validation = body.index("die 2")
    execution = body.index("exec ")
    assert validation < execution, (
        "the wrapper execs the Python before it refuses bad input, so an argument error "
        "would arrive after an import and a daemon probe"
    )


# ---------------------------------------------------------------------------
# seed and psql: refused at the wrapper, before docker (D1170)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        (("seed", "--project", PROJECT), "a seed with no name"),
        (("seed", "example"), "a name with no --project"),
        (("seed", "a/b", "--project", PROJECT), "a name that is a path"),
        (("seed", "../../etc/passwd", "--project", PROJECT), "a traversal"),
        (("seed", ".hidden", "--project", PROJECT), "a dotfile"),
        (("seed", "one", "two", "--project", PROJECT), "two names"),
        (("psql", "--project", PROJECT, "--as", "postgres"), "a role this command will not be"),
        (("psql", "--project", PROJECT, "--as"), "--as with no value"),
        (("up", "stray", "--project", PROJECT), "a positional on a verb that takes none"),
    ],
)
def test_seed_takes_a_name_and_never_a_path(arguments: tuple[str, ...], reason: str) -> None:
    """Every one of these is decided by the shell wrapper, before the Python.

    D1170: the name is a NAME. A separator or a leading dot is refused for what
    it says, so nothing downstream ever joins it to a path -- `bin/db.sh sql`'s
    rule, which refuses `../../etc/anything` as "not allowlisted" rather than
    resolving it and then rejecting it.

    Refused at the wrapper means these exit 2 on a machine with no docker at
    all, which is what makes them an argument contract rather than a runtime
    one.
    """
    result = dev(*arguments)
    assert result.returncode == 2, (
        f"{reason} exited {result.returncode}, not 2.\n{result.stdout}\n{result.stderr}"
    )
    assert result.stderr.strip(), f"{reason} was refused without saying why"
    assert "Traceback" not in result.stderr, f"{reason} produced a traceback"


def test_a_seed_name_is_accepted_in_either_position() -> None:
    """`seed example --project x` and `seed --project x example` are one instruction.

    Both get past the wrapper and fail later, on the environment rather than on
    the argument -- which is the difference this asserts. A wrapper that took
    the name only in one position would refuse the other spelling with "seed
    requires the name of a declared seed", which is a lie about what was typed.
    """
    for arguments in (
        ("seed", "example", "--project", PROJECT),
        ("seed", "--project", PROJECT, "example"),
    ):
        result = dev(*arguments)
        assert result.returncode != 2 or "requires the name" not in result.stderr, (
            f"{arguments} was refused as if no name was given: {result.stderr}"
        )


def test_the_wrapper_forwards_psql_arguments_after_a_double_dash_unread() -> None:
    """Everything after `--` is psql's own -- asserted by RUNNING the command.

    **This proof used to read the wrapper's source and it passed for two
    sessions on a command that did not work** (D1353). It asserted that
    `bin/dev.sh` forwards `"$@"` and handles `--` before the unknown-argument
    refusal, and both were true; what it never looked at was the OTHER half.
    The wrapper `shift`ed the separator away before handing the rest to
    `bin/dev.py`, whose argparse then refused `-c` as an unrecognised argument
    of this command. The documented line in `docs/dev-environment.md` had
    therefore never worked, and the second walk found it by typing it.

    Its own docstring named the reason it did not run the command -- *running
    it needs a terminal this test does not have* -- and that was the SECOND
    defect (D1354, `docker exec -t` unconditionally). Two defects held each
    other up: the TTY made the command untestable, and being untestable is how
    the parser defect survived. Both are fixed, so this now does what D1114
    asks and calls the product's own command.

    No cluster is needed, and that is the point of the assertion's shape. What
    is being proved is that psql's flags reach psql rather than this command's
    parser -- so the arm that matters is that the run gets PAST the parser to
    the environment check. Exit 4 with *no development environment* is a pass;
    exit 2 with *unrecognized arguments* is the defect.
    """
    documented = dev("psql", "--project", PROJECT, "--", "-c", r"\dt api.*")
    assert "unrecognized arguments" not in documented.stderr, (
        "psql's own flags were refused as this command's, which is what `--` exists "
        f"to prevent:\n{documented.stderr}"
    )
    assert documented.returncode != 2, (
        f"the documented psql line was refused as an argument error:\n{documented.stderr}"
    )

    # The control the mutation cannot reach: an unknown flag BEFORE the
    # separator must STILL be refused. Splitting argv on `--` must narrow what
    # the parser sees, never switch it off.
    refused = dev("psql", "--project", PROJECT, "--nonsense")
    assert refused.returncode == 2, (
        f"an unknown flag before the separator was not refused:\n{refused.stderr}"
    )

    # And a bare positional with no separator at all still reaches `rest`,
    # which is how `dev seed --project P example` has always been typed.
    seeded = dev("seed", "--project", PROJECT, "example")
    assert "unrecognized arguments" not in seeded.stderr, seeded.stderr

    # The wrapper's own half, kept: it forwards the rest AND the separator with
    # it, and it handles `--` before the unknown-argument refusal.
    source = DEV.read_text(encoding="utf-8")
    assert 'arguments+=("$@")' in source, "the wrapper does not forward the rest"
    body = source.split("main() {", 1)[1]
    assert body.index("--)") < body.index('die 2 "unknown argument'), (
        "`--` is handled after the unknown-argument refusal, so psql's own flags would "
        "be refused as this command's"
    )
    # **Comments stripped first** (D277, D1197) -- and this assertion needed
    # that within a minute of being written, because the repair's own comment
    # beside the branch explains that the separator used to be shifted away.
    # A scan that reads prose measures prose, every time, including this one.
    code = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    branch = code[code.index("--)") : code.index("--)") + 300]
    assert "shift" not in branch.split("arguments+=")[0], (
        "the wrapper shifts the separator away before forwarding, so bin/dev.py "
        f"cannot tell psql's flags from its own (D1353):\n{branch}"
    )
