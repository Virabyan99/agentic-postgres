"""Operator command surface (runbook §2, §8.5).

Executability is asserted against the **git index**, not the filesystem (plan
decision Q). ``git ls-files --stage`` reports mode ``100755`` regardless of the
filesystem the working tree happens to sit on, and it is what actually decides
the mode on someone else's checkout. A filesystem check would pass or fail for
reasons unrelated to whether the repository is correct.
"""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

#: Every operator command, and Run 8 made the list answerable to the directory.
#:
#: **Twelve commands had accumulated outside it.** `bin/auth-admin.sh`,
#: `bin/rotate-signing-key.sh`, `bin/session-06-check.sh`, `bin/apg-diag.sh`,
#: both halves of `bin/app-contract` and six more Python commands were all
#: absent, so none of them was checked for a CRLF, for a working `--help`, for
#: the executable bit in the git index, or by
#: `test_no_command_documents_a_secret_argument` -- which is the check that
#: enforces D105 and is a large part of why this module exists.
#:
#: Every one of them passed all nine checks the moment it was listed, and that
#: is the uncomfortable half: nothing was wrong, so nothing ever drew attention
#: to the omission. It is D175's shape -- a property kept by review rather than
#: by a test -- and `test_every_command_in_bin_is_covered_by_this_module`
#: converts it into one, because a hand-kept list of files stops covering the
#: directory the first time somebody forgets and says nothing when it does.
SHELL_COMMANDS = (
    "deploy.sh",
    "bin/apg-diag.sh",
    "bin/api.sh",
    "bin/api-contract.sh",
    "bin/app-contract.sh",
    "bin/auth-admin.sh",
    "bin/backup.sh",
    "bin/bootstrap-providers.sh",
    "bin/compose.sh",
    "bin/connect.sh",
    "bin/docker-firewall.sh",
    "bin/doctor.sh",
    "bin/edge.sh",
    "bin/edge-network.sh",
    "bin/lock-dev-deps.sh",
    "bin/lock-versions.sh",
    "bin/materialize-secrets.sh",
    "bin/mcp-contract.sh",
    "bin/database-access.sh",
    "bin/database-ports.sh",
    "bin/db.sh",
    "bin/dev-token.sh",
    "bin/docs.sh",
    "bin/migrate.sh",
    "bin/postgres-bootstrap.sh",
    "bin/project-runtime.sh",
    "bin/provision-host.sh",
    "bin/restore-test.sh",
    "bin/rotate-signing-key.sh",
    "bin/session-01-check.sh",
    "bin/session-02-check.sh",
    "bin/session-03-check.sh",
    "bin/session-04-check.sh",
    "bin/session-05-check.sh",
    "bin/session-06-check.sh",
    "bin/session-07-check.sh",
    "bin/session-08-check.sh",
    "bin/session-09-check.sh",
    "bin/smoke-test.sh",
    "bin/storage-admin.sh",
)

PYTHON_COMMANDS = (
    "bin/api.py",
    "bin/api-contract.py",
    "bin/app-contract.py",
    "bin/auth-admin.py",
    "bin/backup.py",
    "bin/bootstrap-providers.py",
    "bin/database-access.py",
    "bin/database-ports.py",
    "bin/db-verify.py",
    "bin/deploy-project.py",
    "bin/dev-token.py",
    "bin/docs.py",
    "bin/materialize-secrets.py",
    "bin/mcp-contract.py",
    "bin/migrate.py",
    "bin/postgres-bootstrap.py",
    "bin/render-acceptance-matrix.py",
    "bin/render-mcp-catalog.py",
    "bin/render-config.py",
    "bin/render-jwks.py",
    "bin/render-secret-override.py",
    "bin/rotate-signing-key.py",
    "bin/storage-admin.py",
    "bin/write-session-evidence.py",
)

#: Commands that document a future capability and refuse to pretend otherwise.
#:
#: ``bin/bootstrap-providers.sh`` left this tuple in Session 2, ``bin/migrate.sh``
#: in Session 3 and ``bin/connect.sh`` in Session 4, each in the run that
#: implemented it. ADR 0017 records why that is legitimate and what replaced the
#: assertion: all three now carry real command-contract tests, which are stricter
#: than the one they left. Emptying this tuple is not a way to make
#: ``test_future_stub_exits_ten`` pass, and the one command still here is still a
#: stub.
FUTURE_STUBS = ("bin/restore-test.sh",)


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


#: Commands that are INSTALLED rather than run from a checkout.
#:
#: `bin/apg-diag.sh` runs as `/usr/local/bin/apg-diag`, reached through a
#: `NOPASSWD` sudo rule over that exact absolute path (ADR 0071). It has no
#: repository to resolve a root from and must not try: a `BASH_SOURCE`-derived
#: `ROOT_DIR` would point at `/usr/local`, and the whole value of the allowlist
#: is that the file the sudo rule names depends on nothing outside itself.
#:
#: Named here rather than left out of `SHELL_COMMANDS`, which is where it was
#: until Run 8. Out of the list it got none of the other eight checks -- the
#: secret-argument scan included -- for a reason that only ever applied to one
#: of them. An exemption that is written down is a decision; an omission is not.
INSTALLED_COMMANDS = frozenset({"bin/apg-diag.sh"})


@pytest.mark.parametrize("relative", SHELL_COMMANDS)
def test_shell_script_preamble(relative: str) -> None:
    lines = (REPO_ROOT / relative).read_text(encoding="utf-8").splitlines()
    assert lines[0] == "#!/usr/bin/env bash", f"{relative} has the wrong shebang"

    body = "\n".join(lines)
    assert "set -euo pipefail" in body, f"{relative} does not set -euo pipefail"
    if relative not in INSTALLED_COMMANDS:
        assert "BASH_SOURCE" in body, f"{relative} does not resolve its root from BASH_SOURCE"


def test_the_installed_commands_really_run_from_an_absolute_path() -> None:
    """Guard the exemption, so it cannot quietly become a way to opt out.

    An exemption list nothing checks is a list anything can be added to. The
    claim each name here makes is that the command runs from an absolute
    installed path rather than from a checkout, and that claim is checkable:
    the repository has to say what that path is somewhere other than in this
    list.

    **The first version of this asserted the wrong thing** -- that
    `provision-host.sh` installs the file. It does not; ADR 0071 records that the
    copy is placed by hand and that it drifts from the repository until somebody
    replaces it. The test went red on its first run and the premise was corrected
    rather than the assertion loosened, which is the only reason it says anything
    now.
    """
    corpus = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in [
            *sorted((REPO_ROOT / "docs" / "decisions").glob("*.md")),
            *sorted((REPO_ROOT / "tests" / "contract").glob("test_*.py")),
        ]
    )
    for relative in sorted(INSTALLED_COMMANDS):
        installed = f"/usr/local/bin/{Path(relative).stem}"
        assert installed in corpus, (
            f"{relative} is exempted from the repository-root preamble on the ground "
            f"that it runs from an absolute installed path, and nothing in the ADRs or "
            f"the contract tests names {installed}. Either the exemption is wrong or "
            f"the decision behind it was never written down"
        )


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
    [command for command in SHELL_COMMANDS if command != "bin/session-01-check.sh"],
)
def test_help_exits_zero_and_says_something(relative: str) -> None:
    """Every command documents itself, without root and without a host."""
    result = run(str(REPO_ROOT / relative), "--help")
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.strip()) > 40, f"{relative} --help is not informative"


def test_bootstrap_providers_is_no_longer_a_stub() -> None:
    """ADR 0017: it was implemented, so a bare invocation is missing input, not
    an unavailable capability.

    Asserted directly rather than left implicit in ``FUTURE_STUBS``, so that
    removing it from that tuple without implementing it fails here.
    """
    result = run(str(REPO_ROOT / "bin" / "bootstrap-providers.sh"))
    assert result.returncode == 2, (
        f"expected 2 (missing required input), got {result.returncode}. "
        "A 10 here means the command went back to being a stub."
    )
    assert "required" in result.stderr.lower()


def test_connect_is_no_longer_a_stub() -> None:
    """ADR 0017, third application. Asserted here as well as in FUTURE_STUBS.

    A bare invocation used to be exit ``10``, "unavailable this session". It is
    now a missing required input, which is ``2``. Stated directly so that
    removing it from ``FUTURE_STUBS`` without implementing it fails here rather
    than passing quietly, which is the whole reason ADR 0017 exists.
    """
    result = run(str(REPO_ROOT / "bin" / "connect.sh"))
    assert result.returncode == 2, (
        f"expected 2 (missing required input), got {result.returncode}. "
        "A 10 here means the command went back to being a stub."
    )
    assert "required" in result.stderr.lower()


def test_the_remaining_stubs_are_the_ones_later_sessions_own() -> None:
    """Guard the guard: emptying FUTURE_STUBS must not make its tests vacuous."""
    assert set(FUTURE_STUBS) == {"bin/restore-test.sh"}
    assert "bin/bootstrap-providers.sh" not in FUTURE_STUBS
    assert "bin/connect.sh" not in FUTURE_STUBS


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


def test_every_command_in_bin_is_covered_by_this_module() -> None:
    """The lists above must account for the directory, or they cover a subset.

    **Written because they did not.** Run 8 found twelve commands outside them,
    added over Sessions 5 and 6, and every one passed all nine checks the moment
    it was listed. Nothing was broken -- which is precisely why nobody noticed
    for two sessions, and why this cannot be left as a rule somebody remembers.

    It is the same failure this repository keeps producing from the other side:
    not a green test measuring nothing, but a suite of green tests measuring a
    set nobody had stated the boundary of. D211 is the closest relative -- a
    deployment sweep scoped by path, so `tests/security/` was never in it, and
    five green host runs were five reports about a subset.

    Goes red if: a command is added to `bin/` and not listed. That is the whole
    point, and the fix is one line in the list rather than a change here.
    """
    on_disk = {
        f"bin/{path.name}"
        for path in (REPO_ROOT / "bin").iterdir()
        if path.suffix in {".sh", ".py"} and path.is_file()
    }
    listed = set(SHELL_COMMANDS) | set(PYTHON_COMMANDS)

    unlisted = sorted(on_disk - listed)
    assert not unlisted, (
        f"these commands are in bin/ and in neither list, so none of this module's "
        f"checks -- including the secret-argument scan -- applies to them: {unlisted}"
    )

    # And the other direction, which is the cheaper mistake but a real one: a
    # name in the list that no longer exists makes every parametrized case for
    # it error rather than fail, and an errored case is easy to read past.
    missing = sorted(name for name in listed if name.startswith("bin/") and name not in on_disk)
    assert not missing, f"listed but absent from bin/: {missing}"


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


def test_no_command_defines_anything_after_its_entry_point() -> None:
    """A `def` below `if __name__ == "__main__":` does not exist when main runs.

    Python executes a module top to bottom. The guard is a statement like any
    other, so `main()` is called at the line it appears on — and a function
    defined *after* that line has not been bound yet. The failure is a
    `NameError` at runtime, from a file that imports cleanly and passes every
    test that imports it.

    That is exactly how it got here. Four observers were appended to
    `bin/deploy-project.py`, landing below the guard. Every test importing the
    module passed, because `importlib` runs it with `__name__ != "__main__"` so
    the guard never fires and all four definitions execute. The deploy ran it as
    a *script*, reached the guard first, and died with
    `NameError: name 'observe_jwt' is not defined` — after the data plane had
    started, the cluster had been bootstrapped and the migrations had applied.

    So the rule is about execution mode, which no import-based test can see.

    Goes red if: anything is appended to a command below its entry point, which
    is what `cat >>` does by default.
    """
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "bin").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        guard_line = None
        for node in tree.body:
            if (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name)
                and node.test.left.id == "__name__"
            ):
                guard_line = node.lineno
        if guard_line is None:
            continue

        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                if node.lineno > guard_line:
                    offenders.append(
                        f"{path.name}:{node.lineno} {node.name} is defined after the "
                        f"entry point at line {guard_line}"
                    )

    assert not offenders, (
        f"these are not bound when main() runs, and only a script invocation notices: {offenders}"
    )
