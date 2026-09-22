"""`bin/workflow.sh init|validate`, driven as an operator drives them.

**The product's own command, not the functions behind it** (D1114). The
compiler has its own module of proofs; what is asked here is whether the two
verbs an operator actually types do what their help says, with the exit codes
the runbook's convention assigns -- including the four verbs this checkout does
not serve, which must say so rather than fail in a way that reads like a typo.

Nothing here reaches a host, a root, a container or a network. That is the
claim `validate` makes about itself and it is checked by making it: the arms
below run in a temporary directory with no rendered document anywhere.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

COMMAND = REPO_ROOT / "bin" / "workflow.sh"
EXAMPLE = REPO_ROOT / "project.example.yaml"
SECOND = REPO_ROOT / "project.second.example.yaml"


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(COMMAND), *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def test_validate_compiles_the_example_projects_definitions() -> None:
    result = run("validate", "--project", str(EXAMPLE))
    assert result.returncode == 0, result.stderr
    assert "notes-roundtrip.yaml" in result.stdout
    assert "notes-retry.yaml" in result.stdout
    assert re.search(r"lock tools_sha256\s+[0-9a-f]{64}", result.stdout), (
        "validate does not report WHAT it compiled against, so a reader cannot "
        "tell whether the lock moved since"
    )


def test_validate_refuses_naming_the_file_the_step_and_the_reason(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text(
        "schema_version: 1\nname: broken\nversion: 1\ndescription: x\n"
        "steps:\n  - name: the_step\n    capability: not_a_capability@1.0.0\n",
        encoding="utf-8",
    )
    result = run("validate", "--project", str(EXAMPLE), "--file", str(path))
    assert result.returncode == 5, result.stdout + result.stderr
    assert "broken.yaml" in result.stderr
    assert "step the_step" in result.stderr
    assert "compiles no capability named" in result.stderr


def test_a_validate_that_is_going_to_refuse_prints_no_success_sentence(
    tmp_path: Path,
) -> None:
    """**D1403.** A sentence already on the terminal cannot be taken back.

    The refusing run must write NOTHING to stdout: the report is held until
    every file has compiled, so `compiles` cannot appear above a refusal. The
    control is `test_validate_compiles_the_example_projects_definitions`, which
    requires the same sentence to still be printed when nothing refuses -- a
    repair that deleted it would satisfy this half by taking a true report
    away.
    """
    broken = tmp_path / "zzz-broken.yaml"
    broken.write_text(
        "schema_version: 1\nname: broken\nversion: 1\ndescription: x\n"
        "steps:\n  - name: s\n    capability: list_resources@1.0.0\n",
        encoding="utf-8",
    )
    result = run("validate", "--project", str(EXAMPLE), "--file", str(broken))
    assert result.returncode == 5
    assert "compile against this project's lock" not in result.stdout, (
        f"validate wrote a success sentence to stdout and then exited "
        f"{result.returncode}:\n{result.stdout}"
    )


def test_a_project_with_no_migration_set_is_reported_as_declaring_none() -> None:
    """Not zero definitions and not an error: a project without a set has no
    workflows/ directory to have definitions IN, and saying `0` would read as
    a directory somebody emptied."""
    result = run("validate", "--project", str(SECOND))
    assert result.returncode == 0, result.stderr
    assert "declares no migrations.set" in result.stdout


def test_validate_needs_no_host_no_root_and_no_render(tmp_path: Path) -> None:
    """Run from a directory that is not the checkout, with no `.generated`
    anywhere in reach. A lock is COMPUTED from the approved contract and the
    project's own, and discarded."""
    result = subprocess.run(
        [str(COMMAND), "validate", "--project", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert not list(tmp_path.iterdir()), "validate wrote something into the working directory"


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_init_prints_a_skeleton_and_writes_no_file(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(COMMAND), "init", "--project", str(EXAMPLE), "--name", "a-scaffold"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert not list(tmp_path.iterdir()), "init wrote a file; it streams to stdout"

    document = yaml.safe_load(result.stdout)
    assert document["name"] == "a-scaffold"
    assert document["schema_version"] == 1
    assert document["steps"], "a skeleton with no steps teaches nothing"


def test_the_skeleton_names_only_capabilities_the_lock_really_serves() -> None:
    """**The whole point of deriving it from the lock** (the `agent.sh init`
    shape): a scaffold that named a capability the compiler refuses would be a
    scaffold whose first edit is a deletion."""
    from agentic_postgres import workflow_definition as wd

    lock = wd.lock_view_for_project(EXAMPLE)
    served = set(lock.capability_names)

    result = run("init", "--project", str(EXAMPLE))
    assert result.returncode == 0, result.stderr
    document = yaml.safe_load(result.stdout)
    named = {step["capability"] for step in document["steps"]}
    assert named <= served, f"the skeleton names {sorted(named - served)}, which the lock has not"


def test_the_skeleton_never_names_a_capability_that_requires_approval() -> None:
    """`set_note_embedding@1.0.0` is `requires_approval: true` and the compiler
    refuses it until Session 33. A scaffold that suggested it would not
    compile, which is the one thing a scaffold must do."""
    result = run("init", "--project", str(EXAMPLE))
    document = yaml.safe_load(result.stdout)
    assert "set_note_embedding@1.0.0" not in {step["capability"] for step in document["steps"]}


def test_the_skeleton_validates_once_its_placeholders_are_filled(tmp_path: Path) -> None:
    """**The round trip, and it is the strongest thing this module asserts.**

    `init` is only useful if what it prints compiles. The only edits made here
    are the ones its own comments ask for -- the description and the `TODO`
    argument values -- so a skeleton that needed a structural change to compile
    fails this.
    """
    result = run("init", "--project", str(EXAMPLE), "--name", "round-trip")
    assert result.returncode == 0, result.stderr

    filled = result.stdout.replace(": TODO\n", ": a value\n")
    filled = re.sub(r"(?m)^description: >-\n(  .*\n)+", "description: a filled skeleton\n", filled)
    path = tmp_path / "round-trip.yaml"
    path.write_text(filled, encoding="utf-8")

    validated = run("validate", "--project", str(EXAMPLE), "--file", str(path))
    assert validated.returncode == 0, (
        f"the skeleton `init` prints does not compile:\n{validated.stderr}\n\n{filled}"
    )


def test_a_definition_name_the_column_would_refuse_is_refused_here() -> None:
    result = run("init", "--project", str(EXAMPLE), "--name", "Not_A_Name")
    assert result.returncode == 2
    assert "is not a definition name" in result.stderr


# ---------------------------------------------------------------------------
# The four this checkout does not serve
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verb", ["run", "dry-run", "status", "cancel"])
def test_a_verb_this_checkout_does_not_serve_says_which_run_serves_it(verb: str) -> None:
    """Exit 3 -- *a missing local prerequisite* -- and never 10.

    ADR 0017's stub lifecycle is over and `FUTURE_STUBS` is empty; a 10 here
    would reopen it. What this is instead is a verb whose ROUTES do not exist
    yet in this release, which is a prerequisite and says so.
    """
    result = run(verb, "something", "--project-outputs", str(EXAMPLE))
    assert result.returncode == 3, result.stdout + result.stderr
    assert "Session 32 Run 5" in result.stderr
    assert verb in result.stderr


@pytest.mark.parametrize("verb", ["init", "validate", "run", "dry-run", "status", "cancel"])
def test_every_verbs_help_answers_without_a_project(verb: str) -> None:
    """A verb's help is a READ (D1395, D1402, D1405). It is answered before the
    verb is dispatched, so no parser downstream can refuse it for a missing
    required argument -- including the four whose handler exits 3."""
    result = run(verb, "--help")
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.strip()) > 40
    assert verb.split("-")[0] in result.stdout.lower()


# ---------------------------------------------------------------------------
# The command's own shape
# ---------------------------------------------------------------------------


def test_no_verb_is_an_input_error_and_prints_the_usage() -> None:
    result = run()
    assert result.returncode == 2
    assert "a verb is required" in result.stderr
    assert "Usage:" in result.stderr


def test_the_command_holds_no_token_and_no_route() -> None:
    """The token comes from the environment and the base URL from a rendered
    document; a URL or a token spelled in the command would be a second
    authority for an address `naming` owns (ADR 0002)."""
    source = (REPO_ROOT / "bin" / "workflow.py").read_text(encoding="utf-8")
    assert "https://" not in source
    assert "Bearer" not in source
    assert "APG_AGENT_TOKEN" not in source, (
        "the token is read by the HTTP verbs Run 5 builds, not by this checkout's two"
    )
