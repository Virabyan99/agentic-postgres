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

import subprocess
from pathlib import Path

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
