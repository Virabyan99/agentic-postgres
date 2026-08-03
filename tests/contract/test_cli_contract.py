"""Operator command surface (runbook §2, §8.5).

Executability is asserted against the **git index**, not the filesystem (plan
decision Q). ``git ls-files --stage`` reports mode ``100755`` regardless of the
filesystem the working tree happens to sit on, and it is what actually decides
the mode on someone else's checkout. A filesystem check would pass or fail for
reasons unrelated to whether the repository is correct.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SHELL_COMMANDS = (
    "deploy.sh",
    "bin/bootstrap-providers.sh",
    "bin/compose.sh",
    "bin/connect.sh",
    "bin/doctor.sh",
    "bin/lock-dev-deps.sh",
    "bin/lock-versions.sh",
    "bin/migrate.sh",
    "bin/restore-test.sh",
    "bin/session-01-check.sh",
    "bin/smoke-test.sh",
)

PYTHON_COMMANDS = (
    "bin/render-acceptance-matrix.py",
    "bin/render-config.py",
    "bin/write-session-evidence.py",
)

#: Commands that document a future capability and refuse to pretend otherwise.
FUTURE_STUBS = (
    "bin/bootstrap-providers.sh",
    "bin/connect.sh",
    "bin/migrate.sh",
    "bin/restore-test.sh",
)


def run(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env if env is None else {**os.environ, **env},
    )


# ---------------------------------------------------------------------------
# Existence and mode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", SHELL_COMMANDS + PYTHON_COMMANDS)
def test_command_exists(relative: str) -> None:
    assert (REPO_ROOT / relative).is_file(), f"{relative} is missing"


def test_commands_are_executable_in_the_git_index() -> None:
    result = run(
        "git", "ls-files", "--stage", "--", *SHELL_COMMANDS, *PYTHON_COMMANDS, cwd=REPO_ROOT
    )
    assert result.returncode == 0, result.stderr

    modes = {}
    for line in result.stdout.splitlines():
        mode, _, rest = line.partition(" ")
        modes[rest.split("\t", 1)[1]] = mode

    for relative in SHELL_COMMANDS + PYTHON_COMMANDS:
        assert modes.get(relative) == "100755", (
            f"{relative} is {modes.get(relative)} in the git index, expected 100755"
        )


# ---------------------------------------------------------------------------
# Script hygiene (runbook §2 script requirements)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", SHELL_COMMANDS)
def test_shell_script_preamble(relative: str) -> None:
    lines = (REPO_ROOT / relative).read_text(encoding="utf-8").splitlines()
    assert lines[0] == "#!/usr/bin/env bash", f"{relative} has the wrong shebang"

    body = "\n".join(lines)
    assert "set -euo pipefail" in body, f"{relative} does not set -euo pipefail"
    assert "BASH_SOURCE" in body, f"{relative} does not resolve its root from BASH_SOURCE"


@pytest.mark.parametrize("relative", SHELL_COMMANDS)
def test_shell_script_avoids_eval_and_env_dumps(relative: str) -> None:
    """Runbook §2 and §9 check 7."""
    code = "\n".join(
        line
        for line in (REPO_ROOT / relative).read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    )
    assert "eval " not in code, f"{relative} uses eval"
    for dump in ("printenv", "env | ", "set -x", "declare -p"):
        assert dump not in code, f"{relative} may dump the environment via {dump!r}"


@pytest.mark.parametrize("relative", SHELL_COMMANDS)
def test_no_file_uses_crlf(relative: str) -> None:
    assert b"\r" not in (REPO_ROOT / relative).read_bytes(), f"{relative} has CRLF endings"


# ---------------------------------------------------------------------------
# Help and exit codes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        "deploy.sh",
        "bin/bootstrap-providers.sh",
        "bin/compose.sh",
        "bin/connect.sh",
        "bin/doctor.sh",
        "bin/lock-dev-deps.sh",
        "bin/lock-versions.sh",
        "bin/migrate.sh",
        "bin/restore-test.sh",
        "bin/smoke-test.sh",
    ],
)
def test_help_exits_zero_and_says_something(relative: str) -> None:
    result = run(str(REPO_ROOT / relative), "--help")
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.strip()) > 40, f"{relative} --help is not informative"


@pytest.mark.parametrize("relative", FUTURE_STUBS)
def test_future_stub_exits_ten(relative: str) -> None:
    """A stub must not report success for a capability that does not exist."""
    result = run(str(REPO_ROOT / relative))
    assert result.returncode == 10, f"{relative} returned {result.returncode}"


@pytest.mark.parametrize("relative", FUTURE_STUBS)
def test_future_stub_names_its_owning_session(relative: str) -> None:
    result = run(str(REPO_ROOT / relative))
    assert "Session" in result.stderr, f"{relative} does not say when it becomes available"


def test_deploy_requires_render_only() -> None:
    result = run(
        str(REPO_ROOT / "deploy.sh"),
        "--project",
        "project.example.yaml",
        "--capabilities",
        "capabilities.example.yaml",
    )
    assert result.returncode == 10
    assert "render-only" in result.stderr


def test_deploy_rejects_a_positional_argument() -> None:
    """Plan decision V: the source specification's positional form is not accepted."""
    result = run(str(REPO_ROOT / "deploy.sh"), "project.example.yaml")
    assert result.returncode == 2
    assert "unknown argument" in result.stderr


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((), 2),
        (("--bogus",), 2),
        (("--project",), 2),
        (("--project", "p.yaml"), 2),
        (("--capabilities", "c.yaml"), 2),
    ],
)
def test_deploy_invalid_input_exits_two(args: tuple[str, ...], expected: int) -> None:
    assert run(str(REPO_ROOT / "deploy.sh"), *args).returncode == expected


def test_deploy_reports_a_missing_manifest() -> None:
    result = run(
        str(REPO_ROOT / "deploy.sh"),
        "--project",
        "does-not-exist.yaml",
        "--capabilities",
        "capabilities.example.yaml",
        "--render-only",
    )
    assert result.returncode == 2
    assert "not found" in result.stderr


# ---------------------------------------------------------------------------
# Root independence (runbook §8.5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", ["deploy.sh", "bin/doctor.sh", "bin/lock-versions.sh"])
def test_command_works_from_another_directory(relative: str, tmp_path: Path) -> None:
    result = run(str(REPO_ROOT / relative), "--help", cwd=tmp_path)
    assert result.returncode == 0, result.stderr


def test_render_works_from_another_directory(tmp_path: Path) -> None:
    """Relative manifest paths must resolve against the caller's directory."""
    import shutil

    shutil.copy(REPO_ROOT / "project.example.yaml", tmp_path / "p.yaml")
    shutil.copy(REPO_ROOT / "capabilities.example.yaml", tmp_path / "c.yaml")

    result = run(
        str(REPO_ROOT / "deploy.sh"),
        "--project",
        "p.yaml",
        "--capabilities",
        "c.yaml",
        "--render-only",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# No command prints an environment or accepts a secret
# ---------------------------------------------------------------------------


def test_commands_do_not_echo_a_planted_environment_variable() -> None:
    planted = "APG_CANARY_VALUE_bH3x9Qf2"
    for relative in ("bin/doctor.sh", "bin/bootstrap-providers.sh", "bin/connect.sh"):
        result = run(str(REPO_ROOT / relative), env={"APG_CANARY": planted})
        assert planted not in result.stdout + result.stderr, f"{relative} leaked its environment"


def test_no_command_documents_a_secret_argument() -> None:
    """Runbook §2: never accept a secret value as a command-line argument.

    Matched as whole flags, not substrings. A substring check flags
    ``--secrets-namespace``, which takes a namespace *reference* and is exactly
    the safe-reference case runbook §3.6 warns against false-positiving on.
    """
    import re

    forbidden = re.compile(r"--(password|secret|token|api-key|access-key|private-key)(?![a-z-])")
    for relative in SHELL_COMMANDS:
        help_text = run(str(REPO_ROOT / relative), "--help").stdout.lower()
        match = forbidden.search(help_text)
        assert match is None, f"{relative} documents a secret argument: {match.group(0)}"


def test_the_secret_argument_scan_would_catch_a_real_one() -> None:
    """Guard the guard, since the pattern above deliberately allows near-misses."""
    import re

    forbidden = re.compile(r"--(password|secret|token|api-key|access-key|private-key)(?![a-z-])")
    assert forbidden.search("--password VALUE")
    assert forbidden.search("--api-key VALUE")
    assert not forbidden.search("--secrets-namespace REF")
    assert not forbidden.search("--token-ttl-seconds 900")
