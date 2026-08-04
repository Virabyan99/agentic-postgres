"""Shell scripts that embed Python, and the one way they silently stop running.

Several scripts here run Python from a heredoc:

    result="$(PYTHONPATH=... python - arg <<'PYTHON'
    ...
    PYTHON
    )"

``python -`` reads its *program* from standard input. So does a heredoc. Feeding
one a pipe as well gives stdin two claimants, and the heredoc wins: Python reads
the program, never reads the pipe, and the writer on the other side gets SIGPIPE.
Under ``set -o pipefail`` — which every script here sets — that ends the script.

The failure has no error message. It happened mid-check on the deployment host,
after the section header had printed and before the deviation summary, and
survived three ``--apply`` runs looking like output somebody had trimmed.

Data goes to embedded Python through the environment or through arguments.
Never through a pipe.
"""

from __future__ import annotations

import re

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCRIPTS = sorted((REPO_ROOT / "bin").glob("*.sh"))


def logical_lines(text: str) -> list[str]:
    """Join backslash continuations, so one shell command is one string.

    An embedded-Python invocation is routinely spread over three lines by the
    interpreter resolver and the PYTHONPATH assignment. Scanning raw lines would
    look at each fragment separately and see neither the pipe nor the heredoc in
    the company of the other.
    """
    return re.sub(r"\\\n\s*", " ", text).splitlines()


def heredoc_invocations(text: str) -> list[str]:
    """Logical lines that start a quoted Python heredoc."""
    return [line for line in logical_lines(text) if "<<'PYTHON'" in line]


def test_at_least_one_script_embeds_python() -> None:
    """Otherwise the scan below is asserting something about an empty set."""
    assert any(heredoc_invocations(path.read_text(encoding="utf-8")) for path in SCRIPTS)


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda path: path.name)
def test_nothing_is_piped_into_an_embedded_python_program(path) -> None:
    """A pipe and a heredoc cannot both be stdin."""
    for line in heredoc_invocations(path.read_text(encoding="utf-8")):
        before_heredoc = line.split("<<'PYTHON'", 1)[0]
        assert "|" not in before_heredoc, (
            f"{path.name} pipes into a Python heredoc, so the pipe is never read "
            f"and the writer dies of SIGPIPE:\n    {line.strip()}"
        )


def test_the_scan_would_catch_a_real_instance() -> None:
    """Guard the guard, with the exact construction that broke the host."""
    broken = (
        '  unexpected="$(ss -H -lnt 2>/dev/null | PYTHONPATH="${ROOT_DIR}/src" \\\n'
        '    "$(python_bin)" - "${ssh_port}" 80 443 <<\'PYTHON\'\n'
        "print('hello')\n"
        "PYTHON\n"
        '  )"\n'
    )
    invocations = heredoc_invocations(broken)
    assert invocations, "the continuation join no longer produces one logical line"
    assert "|" in invocations[0].split("<<'PYTHON'", 1)[0]


def test_the_scan_does_not_flag_the_correct_form() -> None:
    """The fix passes data in the environment; that must not read as a violation."""
    fixed = (
        '  unexpected="$(\n'
        '    APG_LISTENING_SOCKETS="${listening}" PYTHONPATH="${ROOT_DIR}/src" \\\n'
        '      "$(python_bin)" - "${ssh_port}" 80 443 <<\'PYTHON\'\n'
        "print('hello')\n"
        "PYTHON\n"
        '  )"\n'
    )
    for line in heredoc_invocations(fixed):
        assert "|" not in line.split("<<'PYTHON'", 1)[0]
