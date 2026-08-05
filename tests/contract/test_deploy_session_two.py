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

import subprocess

import pytest

from agentic_postgres import REPO_ROOT
from agentic_postgres.host_config import (
    EDGE_COMPOSE_ENV_KEYS,
    RUNTIME_COMPOSE_ENV_KEYS,
    load_host_manifest,
    runtime_compose_env,
)
from agentic_postgres.rendering import COMPOSE_ENV_KEYS

pytestmark = [pytest.mark.contract, pytest.mark.p0]

DEPLOY = REPO_ROOT / "deploy.sh"
ENTRY_POINT = REPO_ROOT / "bin" / "deploy-session-2.py"

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


@pytest.mark.parametrize("session", ["3", "9", "99"])
def test_a_later_session_is_refused_not_clamped(session: str) -> None:
    """Deploying less than was asked for and reporting success is the worst answer."""
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
    assert result.returncode == 10
    assert "session 2" in result.stderr


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
