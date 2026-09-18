"""The exec discipline (ADR 0218): no product child reads the terminal.

Two halves, and the second is the one that lasts.

**Behavioural.** Against a real container, `run()` with input feeds it and
`run()` without input leaves the child reading a stream that is already at end
of file. The no-input case carries a short timeout: a child handed an
inherited terminal under the measured mechanism does not return, so the
timeout firing IS the failure this module exists to prevent.

**Structural.** An AST scan asserts the class against its DEFINITION rather
than against the fourteen sites that happened to be wrong on 2026-09-18: every
`subprocess` call under `bin/` and `src/` whose argv reaches `docker` or
`compose.sh` either lives in the helper or passes `stdin=`/`input=`. A
targeted list derived from a diff cannot see a caller the diff does not touch
(D1486); a scan over the tree can.

Both scan proofs carry controls, because a scan that looks in the wrong place
reports a clean tree in exactly the same words as a clean tree does (D374).
"""

from __future__ import annotations

import ast
import os
import pty
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.contract.test_image_contracts import LOCK, requires_docker  # noqa: E402

from agentic_postgres import container_exec  # noqa: E402

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

RUNNERS = {"run", "Popen", "check_output", "check_call", "call"}
HELPER = "src/agentic_postgres/container_exec.py"

#: Short on purpose. The failure this module prevents is a child that never
#: returns; a generous timeout would turn that failure into a slow pass.
NO_HANG_TIMEOUT_SECONDS = 15


# ---------------------------------------------------------------------------
# The argv
# ---------------------------------------------------------------------------


def test_the_argv_carries_dash_i_exactly_when_input_is_given() -> None:
    """`-i` is what connects the child's stdin to this process's.

    Rig 30a2 measured that `-i` on a child which does not read stdin is
    harmless and a reading child without `-i` is harmless; the pair is what
    stops. So `-i` is not a style question -- it is half the mechanism, and it
    appears exactly when the other half is a pipe we control.
    """
    assert container_exec.exec_argv("c", "psql") == ["docker", "exec", "c", "psql"]
    assert container_exec.exec_argv("c", "psql", input_given=True) == [
        "docker",
        "exec",
        "-i",
        "c",
        "psql",
    ]


def test_a_tty_is_never_requested_by_run() -> None:
    """`-t` reaches the argv only through `exec_argv(tty=True)`, which `run`
    never passes, and which refuses to be combined with a fed stdin."""
    source = (REPO_ROOT / HELPER).read_text(encoding="utf-8")
    tree = ast.parse(source)
    run_function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    for node in ast.walk(run_function):
        if isinstance(node, ast.keyword) and node.arg == "tty":
            pytest.fail("run() passes tty= to exec_argv; ADR 0218 says it never does")

    assert container_exec.exec_argv("c", "psql", tty=True) == ["docker", "exec", "-it", "c", "psql"]
    with pytest.raises(ValueError, match="two different stdins"):
        container_exec.exec_argv("c", "psql", tty=True, input_given=True)


def test_the_compose_argv_disables_the_pseudo_tty_after_the_run_token() -> None:
    """`-T` immediately after `run`, and an argv with no `run` is refused
    rather than guessed at."""
    argv = container_exec.compose_run_argv(
        "/b/compose.sh", "/r", "--profile", "migration", "run", "--rm", "dbmate", "up"
    )
    assert argv == [
        "/b/compose.sh",
        "/r",
        "--runtime",
        "--profile",
        "migration",
        "run",
        "-T",
        "--rm",
        "dbmate",
        "up",
    ]
    with pytest.raises(ValueError, match="names no run token"):
        container_exec.compose_run_argv("/b/compose.sh", "/r", "ps")


# ---------------------------------------------------------------------------
# Against a real container
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def container() -> str:
    """A throwaway container from the pinned image, removed in `finally`.

    No skip: if docker is absent this module fails, as `test_studio_runtime`
    does. A discipline about running containers that quietly does not run is
    the shape D1236 is the record of.
    """
    name = f"apg-exec-{uuid.uuid4().hex[:10]}"
    started = subprocess.run(
        ["docker", "run", "-d", "--name", name, LOCK["POSTGRES_IMAGE"], "sleep", "300"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert started.returncode == 0, f"could not start the rig container: {started.stderr}"
    try:
        yield name
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name], capture_output=True, text=True, check=False, timeout=60
        )


@requires_docker
def test_input_is_fed_and_reaches_the_child(container: str) -> None:
    """The subject: input supplied, `-i` on the argv, the bytes arrive."""
    sentinel = f"apg-{uuid.uuid4().hex[:12]}"
    result = container_exec.run(container, "cat", input=sentinel)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == sentinel


@requires_docker
def test_stdin_is_closed_when_no_input_is_given(container: str) -> None:
    """The control, and the whole point of the module.

    `cat` with no input reads stdin. With stdin closed it sees end of file at
    once and exits 0. With an inherited terminal it would be stopped by SIGTTIN
    under the measured mechanism and this call would not return -- so the
    timeout is the assertion, not a safety net.
    """
    result = container_exec.run(container, "cat", timeout=NO_HANG_TIMEOUT_SECONDS)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@requires_docker
def test_the_helper_never_leaves_a_dash_i_on_a_child_that_reads_nothing(
    container: str,
) -> None:
    """A second reading of the same rule, from the child's side: a command
    given `-c` does not read stdin, and the argv the helper builds for it
    carries no `-i` at all."""
    result = container_exec.run(container, "sh", "-c", "echo ok", timeout=NO_HANG_TIMEOUT_SECONDS)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
    assert "-i" not in container_exec.exec_argv(container, "sh", "-c", "echo ok")


# ---------------------------------------------------------------------------
# The class guard
# ---------------------------------------------------------------------------


def _reaches_runtime(node: ast.AST) -> str | None:
    if isinstance(node, (ast.List, ast.Tuple)):
        for element in node.elts[:3]:
            for inner in ast.walk(element):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    if inner.value == "docker":
                        return "docker"
                    if inner.value.endswith("compose.sh"):
                        return "compose.sh"
    return None


def scan_source(source: str, label: str) -> list[str]:
    """Every `subprocess.*` call in `source` whose argv reaches docker or
    compose.sh and which passes neither `stdin=` nor `input=`.

    Parsed rather than grepped, for D204's reason: several of these argvs are
    spread over twenty lines with comments between their elements, which is
    not something a regex reads correctly.
    """
    tree = ast.parse(source)

    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            what = _reaches_runtime(node.value)
            if what:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bound[target.id] = what

    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr in RUNNERS
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
        ):
            continue
        first = node.args[0]
        what = _reaches_runtime(first)
        if what is None and isinstance(first, ast.Name):
            what = bound.get(first.id)
        if what is None:
            continue
        keywords = {keyword.arg for keyword in node.keywords}
        if "stdin" in keywords or "input" in keywords:
            continue
        findings.append(f"{label}:{node.lineno} runs {what} with an inherited stdin")
    return findings


def product_modules() -> list[Path]:
    modules = sorted((REPO_ROOT / "bin").glob("*.py"))
    modules += sorted((REPO_ROOT / "src" / "agentic_postgres").rglob("*.py"))
    return modules


def test_the_scan_finds_no_docker_or_compose_subprocess_outside_the_helper() -> None:
    """ADR 0218's class, guarded against its definition.

    Goes red when somebody writes the fortieth call site. That is the whole
    reason this is a scan and not a list: on 2026-09-18 the inventory was
    fourteen unguarded sites across nine files, and five of those files were
    not named in the plan that set out to repair them.
    """
    modules = product_modules()
    # Anti-vacuity on the SEARCH, not only on the matcher: a scan aimed at an
    # empty list reports a clean tree in exactly the words a clean tree uses.
    names = {str(module.relative_to(REPO_ROOT)) for module in modules}
    assert len(modules) > 80, f"the scan is looking at {len(modules)} modules; it should be ~100"
    for required in ("bin/backup.py", "bin/deploy-project.py", HELPER):
        assert required in names, f"the scan does not reach {required}"

    problems: list[str] = []
    for module in modules:
        relative = str(module.relative_to(REPO_ROOT))
        if relative == HELPER:
            continue
        problems.extend(scan_source(module.read_text(encoding="utf-8"), relative))

    assert not problems, "these run a container runtime with an inherited stdin:\n" + "\n".join(
        problems
    )


def test_the_scan_finds_the_helpers_own_call() -> None:
    """Anti-vacuity, against the real tree (D374).

    `container_exec.py` is excluded by name from the guard above. If the scan
    were broken -- wrong node type, wrong attribute, looking at nothing -- it
    would report the helper as clean too, and the guard's silence would mean
    nothing. The helper's own `subprocess.run` DOES pass `stdin=`, so this
    asserts the scan SEES it rather than that it complains about it.
    """
    source = (REPO_ROOT / HELPER).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in RUNNERS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]
    assert len(calls) >= 2, "the helper no longer runs subprocess; this scan is aimed at nothing"
    assert scan_source(source, HELPER) == [], (
        "the helper itself runs a container runtime with an inherited stdin"
    )


def test_the_scan_catches_a_synthetic_inherited_stdin(tmp_path: Path) -> None:
    """The other control: a module the scan MUST catch, fed to the same
    function the guard uses. A guard nobody has seen fail is a guard nobody has
    tested."""
    synthetic = textwrap.dedent(
        """
        import subprocess

        def careless(container):
            return subprocess.run(
                ["docker", "exec", "-i", container, "cat"],
                capture_output=True,
            )
        """
    )
    findings = scan_source(synthetic, "synthetic.py")
    assert len(findings) == 1, f"the scan missed a plain inherited stdin: {findings}"
    assert "docker" in findings[0]

    guarded = synthetic.replace("capture_output=True,", "stdin=subprocess.DEVNULL,")
    assert scan_source(guarded, "synthetic.py") == [], (
        "the scan reports a call that closes stdin, so it would never go green"
    )


def test_the_scan_reads_an_argv_bound_to_a_name(tmp_path: Path) -> None:
    """`command = [...]` then `subprocess.run(command)` is the shape four of
    the real sites used, and a scan that only looked at the call's own literal
    would have called every one of them clean."""
    synthetic = textwrap.dedent(
        """
        import subprocess

        def careless(container):
            command = ["docker", "exec", container, "psql"]
            return subprocess.run(command, capture_output=True)
        """
    )
    findings = scan_source(synthetic, "synthetic.py")
    assert len(findings) == 1, f"the scan does not follow a bound argv: {findings}"


# ---------------------------------------------------------------------------
# The shell half
# ---------------------------------------------------------------------------


def test_the_shell_library_and_the_module_print_the_same_sentence() -> None:
    """`bin/lib/tty-guard.sh` holds D972's refusal, MOVED from `deploy.sh`.

    The two texts are compared rather than trusted to match: a message that
    drifts is a message an operator searches the runbook for and does not find.
    """
    library = (REPO_ROOT / "bin" / "lib" / "tty-guard.sh").read_text(encoding="utf-8")
    assert container_exec.MIXED_TERMINAL_SHAPE_MESSAGE in library

    deploy = (REPO_ROOT / "deploy.sh").read_text(encoding="utf-8")
    assert 'refuse_mixed_terminal_shape "--through-session"' in deploy
    assert "bin/lib/tty-guard.sh" in deploy
    assert container_exec.MIXED_TERMINAL_SHAPE_MESSAGE not in deploy, (
        "deploy.sh still spells the message; it was supposed to MOVE to the library"
    )


def test_the_guard_library_is_not_a_command() -> None:
    """It is sourced, so it carries no shebang and is not executable.
    `test_cli_contract`'s non-recursive `iterdir` over `bin/` must not see it."""
    library = REPO_ROOT / "bin" / "lib" / "tty-guard.sh"
    text = library.read_text(encoding="utf-8")
    assert not text.startswith("#!"), "a sourced library has no shebang"
    assert "shellcheck shell=bash" in text


def test_run_closes_stdin_when_no_input_is_given(monkeypatch: pytest.MonkeyPatch) -> None:
    """The structural half, and the one a mutation can be caught by.

    `test_stdin_is_closed_when_no_input_is_given` runs a real container and is
    worth having, but it cannot fail when `stdin=DEVNULL` is deleted: under
    pytest this process's stdin is not a terminal, so the child reaches end of
    file whether it inherited one or not. The mechanism only bites where stdin
    IS a terminal, which a test process is not.

    So the argument is read directly. Measured by the Run 3 battery: deleting
    `stdin=DEVNULL` from `run()` left every other proof in this module green.
    """
    seen: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(container_exec.subprocess, "run", fake_run)

    container_exec.run("c", "psql")
    assert seen["stdin"] is subprocess.DEVNULL, (
        "run() without input must close stdin; ADR 0218 is the whole of this module"
    )
    assert seen["input"] is None
    assert "-i" not in seen["argv"]

    seen.clear()
    container_exec.run("c", "cat", input="hello")
    assert seen["stdin"] is None, "with input, subprocess supplies the pipe"
    assert seen["input"] == "hello"
    assert "-i" in seen["argv"]


@pytest.mark.skipif(os.name != "posix", reason="a pty is a POSIX object")
def test_the_guard_refuses_a_terminal_on_stdout_with_only_stderr_redirected() -> None:
    """The arm of D972's condition that no passing test had executed.

    `test_printed_commands.py`'s proof redirects with `capture_output=True`,
    which pipes stdout AND stderr, so `[ ! -t 1 ]` is true and the `|| [ ! -t 2 ]`
    half is never reached. The Run 3 battery weakened the guard to test stdout
    alone and that proof stayed green.

    Here stdin and stdout are the same pty and only stderr is a pipe, so the
    refusal can only come from the second half of the condition.
    """
    leader, follower = pty.openpty()
    read_end, write_end = os.pipe()
    try:
        result = subprocess.run(
            [
                str(REPO_ROOT / "deploy.sh"),
                "--host",
                str(REPO_ROOT / "host.example.yaml"),
                "--project",
                str(REPO_ROOT / "project.example.yaml"),
                "--capabilities",
                str(REPO_ROOT / "capabilities.example.yaml"),
                "--through-session",
                "1",
            ],
            stdin=follower,
            stdout=follower,
            stderr=write_end,
            text=True,
            timeout=60,
            check=False,
        )
        os.close(write_end)
        write_end = -1
        captured = os.read(read_end, 65536).decode("utf-8", "replace")
    finally:
        os.close(leader)
        os.close(follower)
        os.close(read_end)
        if write_end != -1:
            os.close(write_end)

    assert result.returncode == 2, f"stderr-only redirection was not refused: {captured!r}"
    assert "D972" in captured and "unredirected" in captured
