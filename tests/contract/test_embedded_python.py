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


def test_every_embedded_python_program_compiles() -> None:
    """A program built by string concatenation is a program nobody has parsed.

    This file has compiled Python embedded in *shell* scripts since Session 2.
    Python embedded in **Python** had no such rule, and the first one shipped
    broken: `.rstrip("\\n")` written into a `-c` argument from Python source is
    a newline *character*, so the program arrived split across two lines and
    died with `unterminated string literal` -- on a host, in step 5, after two
    images had been built (D205).

    Nothing offline could have seen it. The tests written beside it assert the
    call's *shape*: the secret goes on stdin, `-i` is present, no element of the
    argument vector is built from the credential. Every one of those was true.
    A shape is not a program.

    Scoped to `python -c` in `bin/*.py`, found through the syntax tree rather
    than by matching text, so a program assembled from several adjacent string
    literals -- which is exactly how the broken one was written -- is compiled
    as the single string Python actually builds.
    """
    import ast

    programs: list[tuple[str, str]] = []
    for source in sorted((REPO_ROOT / "bin").glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.List):
                continue
            values = [
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
            for index, value in enumerate(values):
                # `-c` alone is not enough: psql takes one too, and the first
                # version of this scan compiled `psql -c "SELECT ..."` as Python
                # and reported the SQL as a syntax error. The interpreter has to
                # be named immediately before the flag.
                if (
                    value == "-c"
                    and index >= 1
                    and values[index - 1] in {"python", "python3"}
                    and index + 1 < len(values)
                ):
                    programs.append((source.name, values[index + 1]))

    assert programs, "no `python -c` program found in bin/; this compiled nothing"

    for name, program in programs:
        try:
            compile(program, f"<{name}>", "exec")
        except SyntaxError as error:
            raise AssertionError(
                f"{name} builds a `python -c` program that does not parse: {error}. "
                f"The program was: {program!r}"
            ) from error


def test_the_compile_scan_would_catch_a_real_instance() -> None:
    """The control for the scan above.

    A scan that found nothing, or that compiled the wrong string, would pass
    every time. This is the exact defect D205 shipped: a literal newline where
    a two-character escape belonged.
    """
    import ast

    source = 'subprocess.run(["python", "-c", "print(\'a\\nb\')"])'
    tree = ast.parse(source)
    found = [
        element.value
        for node in ast.walk(tree)
        if isinstance(node, ast.List)
        for element in node.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    ]
    assert "-c" in found
    broken = found[found.index("-c") + 1]
    with pytest.raises(SyntaxError):
        compile(broken, "<control>", "exec")
