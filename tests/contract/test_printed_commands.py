"""A printed command is run as printed (D975, Session 17 Run 7).

`--render-runtime-only` ended with a hint reading `--host <host.yaml>`. Pasted
verbatim, the angle brackets are shell redirections: `< host.yaml` fed the
manifest to stdin and `> --instance-uuid` created a file of that name in the
checkout, so the next deploy refused a dirty release. The process held the
real path the whole time.

The rule these proofs keep: a command printed by a release for an operator to
run carries the values the process has, and a placeholder only for a value it
does not. The scan is over the deploy driver's own print statements, and the
control is the usage text of `deploy.sh`, where `<project.yaml>` is legitimate
because the script cannot know the path before it is given one.
"""

from __future__ import annotations

import os
import pty
import re
import subprocess

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p1]

DRIVER = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
DEPLOY_SH = (REPO_ROOT / "deploy.sh").read_text(encoding="utf-8")

#: Every driver that prints a command for an operator to run next.
#:
#: **The scan was over the deploy driver alone until Session 23** (D1208), when
#: the capture and the compile each gained a printed `bin/apg.sh generate
#: --project <path>` -- the same shape D975 was written about, in two files the
#: rule did not reach. Widening the scan to the drivers that actually print a
#: command is what the non-negotiables call a widening to a measured set; the
#: rule itself is unchanged and no assertion was relaxed to admit them.
PRINTING_DRIVERS = {
    name: (REPO_ROOT / "bin" / f"{name}.py").read_text(encoding="utf-8")
    for name in ("deploy-project", "api-contract", "mcp-contract")
}

# `--flag <placeholder>` inside a print( ... ) call. Multi-line prints are
# joined by the DOTALL span from `print(` to the next `)` at line end.
PRINTED = re.compile(r"print\((.*?)\)\n", re.DOTALL)
PLACEHOLDER_ARGUMENT = re.compile(r"--[a-z-]+ <[a-z.-]+>")


def test_no_printed_command_carries_a_placeholder_for_a_value_the_process_holds() -> None:
    for name, source in PRINTING_DRIVERS.items():
        offenders = [
            match.group(0)
            for block in PRINTED.findall(source)
            for match in PLACEHOLDER_ARGUMENT.finditer(block)
            # `--username <name>`: the deploy cannot know the administrator's
            # name, and the hint says so. That placeholder is the one the rule
            # allows.
            if match.group(0) not in {"--username <name>", "--display-name <name>"}
        ]
        assert not offenders, (
            f"{name}.py prints {offenders}: a placeholder in angle brackets is a "
            "shell redirection when pasted, and the process holds the real value (D975)"
        )
    assert "--host {arguments.host}" in DRIVER, "the verify hint no longer prints the host path"


def test_the_generate_hook_prints_the_path_the_process_was_given() -> None:
    """D1208, and the reason the scan above was widened to reach these two.

    The capture and the compile each end by naming the command that regenerates
    the project's client. A `--project <project.yaml>` there would be a
    redirection when pasted -- and both processes hold the real path, because
    it is the argument they were invoked with. So this asserts the shape the
    scan cannot: that the flag is followed by an INTERPOLATION and not a
    literal, in each of the two.
    """
    for name, holder in (
        ("api-contract", "{project_path}"),
        ("mcp-contract", "{arguments.project}"),
    ):
        source = PRINTING_DRIVERS[name]
        printed = f"bin/apg.sh generate --project {holder}"
        assert printed in source, (
            f"{name}.py does not print the generate step with the path it holds. "
            f"Expected {printed!r}; a literal placeholder would be a redirection "
            "when the operator pastes the line"
        )


def test_the_control_placeholder_in_usage_text_is_still_there() -> None:
    """The scan is not a ban on angle brackets: usage text describes a value
    the script has not been given yet, and that is the one legitimate case."""
    assert "--project <project.yaml>" in DEPLOY_SH


@pytest.mark.skipif(os.name != "posix", reason="a pty is a POSIX object")
def test_a_deploy_with_a_terminal_on_stdin_and_redirected_output_is_refused() -> None:
    """D972. Under sudo's use_pty, stdin at a terminal with stdout redirected
    runs the command in the background of the pty, and its first `docker exec
    -i` is stopped with SIGTTIN. `deploy.sh` refuses that exact shape before it
    reaches root. The control runs the same arguments with no terminal anywhere
    and must get past that check to the next refusal, which is root."""
    manifest = REPO_ROOT / "project.example.yaml"
    capabilities = REPO_ROOT / "capabilities.example.yaml"
    host = REPO_ROOT / "host.example.yaml"
    assert manifest.is_file() and capabilities.is_file() and host.is_file()
    arguments = [
        str(REPO_ROOT / "deploy.sh"),
        "--host",
        str(host),
        "--project",
        str(manifest),
        "--capabilities",
        str(capabilities),
        "--through-session",
        "1",
    ]

    leader, follower = pty.openpty()
    try:
        shaped = subprocess.run(
            arguments, stdin=follower, capture_output=True, text=True, timeout=60, check=False
        )
    finally:
        os.close(leader)
        os.close(follower)
    assert shaped.returncode == 2, shaped.stderr
    assert "D972" in shaped.stderr and "unredirected" in shaped.stderr

    # Control: no terminal on stdin, same arguments. The shape is not this
    # one, so the refusal that arrives is the next one in the file.
    control = subprocess.run(
        arguments,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert control.returncode == 3, control.stderr
    assert "requires root" in control.stderr
    assert "D972" not in control.stderr
