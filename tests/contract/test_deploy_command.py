"""The deploy command's Session 2 surface, and what it refuses to do for you.

Two properties matter more than the happy path, which only a host can exercise.

**It does not create its own preconditions.** The edge plane, the provider
bootstrap and the secret generation are separate commands run beforehand. A
deploy that quietly performed them would mean something different on a fresh
host than on a redeploy, and a failure halfway would leave nobody able to say
which half ran. Each precondition is checked and named, with the command that
satisfies it.

**Nothing is clamped.** `--through-session 9` is refused rather than quietly
reduced to what this release can do — deploying less than was asked for and
reporting success is the failure mode that gets discovered in production.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from agentic_postgres import CURRENT_SESSION, REPO_ROOT
from agentic_postgres.host_config import (
    EDGE_COMPOSE_ENV_KEYS,
    RUNTIME_COMPOSE_ENV_KEYS,
    load_host_manifest,
    runtime_compose_env,
)
from agentic_postgres.rendering import COMPOSE_ENV_KEYS

pytestmark = [pytest.mark.contract, pytest.mark.p0]

DEPLOY = REPO_ROOT / "deploy.sh"
ENTRY_POINT = REPO_ROOT / "bin" / "deploy-project.py"

PROJECT = "project.example.yaml"
CAPABILITIES = "capabilities.example.yaml"
HOST = "host.example.yaml"


def deploy(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(DEPLOY), *args], capture_output=True, text=True, check=False, cwd=REPO_ROOT
    )


# ---------------------------------------------------------------------------
# The command surface
# ---------------------------------------------------------------------------


def test_help_documents_both_modes() -> None:
    result = deploy("--help")
    assert result.returncode == 0
    assert "--render-only" in result.stdout
    assert "--through-session" in result.stdout


def test_render_only_still_needs_no_host_and_no_root() -> None:
    """Session 1's entire surface has to keep working unchanged."""
    result = deploy("--project", PROJECT, "--capabilities", CAPABILITIES, "--render-only")
    assert result.returncode == 0, result.stderr


def test_neither_mode_is_refused_with_a_usable_message() -> None:
    result = deploy("--project", PROJECT, "--capabilities", CAPABILITIES)
    assert result.returncode == 10
    assert "--render-only" in result.stderr and "--through-session" in result.stderr


def test_both_modes_at_once_is_refused() -> None:
    """They ask for different things; guessing which was meant is worse."""
    result = deploy(
        "--project",
        PROJECT,
        "--capabilities",
        CAPABILITIES,
        "--render-only",
        "--through-session",
        "2",
    )
    assert result.returncode == 2


def test_deploying_requires_a_host_manifest() -> None:
    result = deploy("--project", PROJECT, "--capabilities", CAPABILITIES, "--through-session", "2")
    assert result.returncode == 2
    assert "--host" in result.stderr


@pytest.mark.parametrize("beyond", [1, 2, 97])
def test_a_later_session_is_refused_not_clamped(beyond: int) -> None:
    """Deploying less than was asked for and reporting success is the worst answer.

    Parametrized on `CURRENT_SESSION + n` rather than on the literals 3, 9, 99.
    Those were correct while the ceiling was 2 and became a test of the wrong
    number the moment the release implemented Session 3 -- the same duplicated
    constant the script itself no longer holds (D59). What is asserted is the
    rule: one past the ceiling is refused, and the refusal names the ceiling.
    """
    result = deploy(
        "--host",
        HOST,
        "--project",
        PROJECT,
        "--capabilities",
        CAPABILITIES,
        "--through-session",
        str(CURRENT_SESSION + beyond),
    )
    assert result.returncode == 10
    assert f"session {CURRENT_SESSION}" in result.stderr


def test_the_session_this_release_implements_is_not_refused() -> None:
    """The other half, and the half a ceiling test alone cannot give you.

    A release that refused its own session would fail every deployment of the
    work it contains, and every assertion above would still pass. This gets as
    far as the root check, which is the first thing after the ceiling.
    """
    result = deploy(
        "--host",
        HOST,
        "--project",
        PROJECT,
        "--capabilities",
        CAPABILITIES,
        "--through-session",
        str(CURRENT_SESSION),
    )
    assert result.returncode == 3, result.stderr
    assert "root" in result.stderr


@pytest.mark.parametrize("session", ["two", "2.0", "-1", ""])
def test_a_session_that_is_not_a_number_is_an_input_error(session: str) -> None:
    result = deploy(
        "--host",
        HOST,
        "--project",
        PROJECT,
        "--capabilities",
        CAPABILITIES,
        "--through-session",
        session,
    )
    assert result.returncode == 2


def test_deploying_refuses_without_root() -> None:
    """Checked after the arguments, so a typo does not require root to discover."""
    result = deploy(
        "--host",
        HOST,
        "--project",
        PROJECT,
        "--capabilities",
        CAPABILITIES,
        "--through-session",
        "2",
    )
    assert result.returncode == 3
    assert "root" in result.stderr


# ---------------------------------------------------------------------------
# Preconditions are named, never created
# ---------------------------------------------------------------------------


def test_every_precondition_names_the_command_that_satisfies_it() -> None:
    """A refusal an operator cannot act on is a refusal they will work around."""
    source = ENTRY_POINT.read_text(encoding="utf-8")
    for command in ("bin/edge.sh", "bin/bootstrap-providers.sh", "bin/materialize-secrets.sh"):
        assert command in source, f"no precondition failure mentions {command}"


def test_the_deploy_does_not_run_its_own_preconditions(code_only) -> None:
    """Naming them in an error message is different from invoking them."""
    source = code_only(ENTRY_POINT.read_text(encoding="utf-8"))
    for command in ("edge.sh", "bootstrap-providers.sh", "materialize-secrets.sh"):
        invocations = [
            line
            for line in source.splitlines()
            if command in line and "run(" in line.replace(" ", "")
        ]
        assert not invocations, f"the deploy invokes {command} itself: {invocations}"


def test_a_missing_generation_manifest_is_a_precondition_not_a_crash() -> None:
    """A generation written before this release has no manifest.json.

    That is a state an upgraded host really reaches, and the deployed document
    would otherwise name a path that does not resolve.
    """
    source = ENTRY_POINT.read_text(encoding="utf-8")
    assert "predates this release" in source


# ---------------------------------------------------------------------------
# The root-owned runtime env (ADR 0013 / D7)
# ---------------------------------------------------------------------------


def test_the_runtime_env_carries_exactly_the_host_derived_keys() -> None:
    document = load_host_manifest(REPO_ROOT / HOST)
    text = runtime_compose_env(document).decode("utf-8")
    keys = {
        line.split("=", 1)[0] for line in text.splitlines() if line and not line.startswith("#")
    }
    assert keys == set(RUNTIME_COMPOSE_ENV_KEYS)


def test_the_three_env_files_are_disjoint() -> None:
    """Three files reach `--runtime` mode; no ordering may shadow anything.

    Asserted three ways rather than one, because the pair that overlaps is
    never the pair anyone thought to check.
    """
    versions = {
        line.split("=", 1)[0]
        for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    }
    project = set(COMPOSE_ENV_KEYS)
    runtime = set(RUNTIME_COMPOSE_ENV_KEYS)
    edge = set(EDGE_COMPOSE_ENV_KEYS)

    assert not project & runtime
    assert not project & versions
    assert not runtime & versions
    assert not runtime & edge


def test_the_runtime_env_is_not_written_into_the_rendered_directory() -> None:
    """An operator who can write rendered output must not choose the resolver."""
    source = ENTRY_POINT.read_text(encoding="utf-8")
    assert "state_directory / " in source
    assert ".generated" not in source.split("runtime_compose_env")[1].split("\n")[0]


# ---------------------------------------------------------------------------
# --render-runtime-only (Session 4 Run 4, D95)
# ---------------------------------------------------------------------------


#: The operator entry point, which is not `ENTRY_POINT`: that is
#: `bin/deploy-project.py`, the program deploy.sh execs. The mode guards below
#: belong to the shell script, so they are driven through it. Naming this
#: `deploy` as well would redefine the helper every earlier test in this file
#: uses -- which it did, and seven of them started measuring the wrong program.
OPERATOR_ENTRY_POINT = REPO_ROOT / "deploy.sh"


def deploy_sh(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(OPERATOR_ENTRY_POINT), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )


def test_render_only_still_works_through_the_operator_entry_point() -> None:
    """The standing non-negotiable, asserted beside the mode that could break it.

    A second render mode is exactly the change that would quietly make the first
    one require a host. `test_render_only_still_needs_no_host_and_no_root` above
    already asserts this through `bin/deploy-project.py`; this asserts it through
    `deploy.sh`, which is where the new mode's guards live and therefore where a
    guard could catch the wrong mode.

    Named differently from that one deliberately. The first version of this test
    reused its name, which is not a duplicate so much as a deletion: the later
    definition silently replaced the earlier, and the property everyone thought
    was covered twice was covered once.
    """
    result = deploy_sh(
        "--project",
        "project.example.yaml",
        "--capabilities",
        "capabilities.example.yaml",
        "--render-only",
    )
    assert result.returncode == 0, result.stderr


def test_a_runtime_render_without_a_host_is_refused() -> None:
    result = deploy_sh(
        "--project",
        "project.example.yaml",
        "--capabilities",
        "capabilities.example.yaml",
        "--render-runtime-only",
    )
    assert result.returncode == 2
    assert "--host" in result.stderr


def test_a_runtime_render_as_an_ordinary_user_is_refused() -> None:
    """Root, and said before anything is read rather than after.

    This writes the root-owned runtime override and the host port registry. A
    permission error from halfway through would leave an operator asking which
    half ran.
    """
    if os.geteuid() == 0:
        pytest.skip("this asserts the refusal an ordinary user gets")
    result = deploy_sh(
        "--project",
        "project.example.yaml",
        "--capabilities",
        "capabilities.example.yaml",
        "--host",
        "host.example.yaml",
        "--render-runtime-only",
    )
    assert result.returncode == 3
    assert "root" in result.stderr


def test_the_two_render_modes_are_not_combinable() -> None:
    """They ask for different things, and one of them needs a host.

    Accepting both would have to mean one silently winning, and which one is
    not something an operator should have to know.
    """
    result = deploy_sh(
        "--project",
        "project.example.yaml",
        "--capabilities",
        "capabilities.example.yaml",
        "--host",
        "host.example.yaml",
        "--render-only",
        "--render-runtime-only",
    )
    assert result.returncode == 2


def test_a_runtime_render_does_not_deploy() -> None:
    """Asserted on the source, because the behaviour needs a host to observe.

    The four things it must not do are the four that would make a failed run
    unrecoverable: materialize a secret, start a container, mark an allocation
    active, or publish readiness. Each is a claim about a running system, and
    nothing is running differently when this returns.
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    body = source.split("def render_runtime_only(")[1].split("\ndef ")[0]

    # Tokens, not words. The first version of this scan looked for "ready" and
    # matched "already" in a comment, which is a test failing for a reason that
    # has nothing to do with the property.
    for forbidden in ("materialize-secrets", "project-runtime.sh", "port_allocations.activate"):
        assert forbidden not in body, (
            f"the runtime render references {forbidden!r}; it must reserve and render only"
        )
    assert '"ready"' not in body, "the runtime render publishes readiness"
    assert "database-ports.sh" in body
    assert "publications=" in body
