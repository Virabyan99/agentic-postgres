"""`DX-COMPLETE-001` -- a completion script that keeps no list (ADR 0207 §2).

**The thing under test is an absence.** Any generator can emit a completion
script; what this one must not do is emit the *answers*. A script with the verbs
baked into it works perfectly on the day it is printed and is wrong the first
time somebody adds a command to `bin/` -- silently, because a completion that
offers too little looks like a shell that has not been reloaded.

So the proofs are: the script offers what `--list` offers, at the moment it is
asked; it offers a verb's flags from that verb's own `--help`; and it contains
neither. The last one is what makes the first two more than a snapshot.

Everything here drives the printed script in a real `bash -c`, with
`COMP_WORDS` and `COMP_CWORD` set the way bash sets them, because a completion
function that is only read is a completion function that has never run.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

APG = REPO_ROOT / "bin" / "apg.sh"
COMPLETION = REPO_ROOT / "bin" / "completion.sh"


def _environment() -> dict[str, str]:
    """Never the test process's own `APG_PROJECT` (the dispatcher reads it)."""
    return {key: value for key, value in os.environ.items() if key != "APG_PROJECT"}


def run_apg(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(APG), *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=_environment(),
    )


@pytest.fixture(scope="module")
def printed() -> str:
    """The script, printed through the dispatcher rather than by calling the file.

    D1114: a proof calls the product's own command. An operator reaches this as
    `bin/apg.sh completion bash`, so that is what is run.
    """
    result = run_apg("completion", "bash")
    assert result.returncode == 0, result.stderr
    assert result.stderr == "", f"the script came with commentary on stderr: {result.stderr}"
    return result.stdout


def verbs() -> list[str]:
    result = run_apg("--list")
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


def complete(printed: str, script_path: Path, *words: str) -> list[str]:
    """Source the script in bash, set the variables bash sets, read COMPREPLY.

    `COMP_CWORD` is the index of the word being completed, which is the LAST
    one -- an empty final word is "the cursor is at a fresh word", which is what
    a bare TAB looks like.
    """
    script_path.write_text(printed, encoding="utf-8")
    words_literal = " ".join(f"'{word}'" for word in words)
    driver = (
        f"source '{script_path}'\n"
        f"COMP_WORDS=({words_literal})\n"
        f"COMP_CWORD={len(words) - 1}\n"
        "_apg_complete\n"
        'printf "%s\\n" "${COMPREPLY[@]}"\n'
    )
    result = subprocess.run(
        ["bash", "-c", driver],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=_environment(),
    )
    assert result.returncode == 0, f"the driver failed: {result.stderr}"
    return [line for line in result.stdout.splitlines() if line]


def registrations(printed: str, script_path: Path) -> list[str]:
    """What `complete -p` reports after sourcing the script, one line per name.

    Calling the function directly proves it computes the right answer. Only this
    proves bash would ever call it.
    """
    script_path.write_text(printed, encoding="utf-8")
    driver = (
        f"source '{script_path}'\n"
        "complete -p bin/apg.sh 2>/dev/null || true\n"
        "complete -p apg 2>/dev/null || true\n"
    )
    result = subprocess.run(
        ["bash", "-c", driver],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=_environment(),
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def test_completion_is_a_verb_of_the_dispatcher() -> None:
    """It is reached the way an operator reaches it, and it installs nothing."""
    assert "completion" in verbs()

    helped = run_apg("completion", "--help")
    assert helped.returncode == 0
    assert len(helped.stdout.strip()) > 40
    assert "installs nothing" in helped.stdout, (
        "the usage no longer says that it writes no file, which is the decision"
    )

    before = sorted(path.name for path in Path.home().glob(".bash*"))
    run_apg("completion", "bash")
    after = sorted(path.name for path in Path.home().glob(".bash*"))
    assert before == after, "printing the script touched the caller's shell configuration"


def test_the_script_embeds_no_verb_and_no_flag(printed: str) -> None:
    """The absence that makes the rest more than a snapshot.

    Comments are stripped first (D1197): the script's header explains what it
    does, and explaining it requires saying words like *completion*. What may
    not appear is a verb or a flag in the CODE, where it would be an answer
    rather than a description.

    `/dev/null` is not a verb named `dev`, so the boundary excludes a name
    preceded by a slash -- the one place a verb-shaped word is a path.
    """
    code = "\n".join(line for line in printed.splitlines() if not line.lstrip().startswith("#"))

    embedded = [
        verb for verb in verbs() if re.search(rf"(?<![\w/-]){re.escape(verb)}(?![\w/-])", code)
    ]
    assert not embedded, (
        f"the printed script names these verbs: {embedded}. A baked-in roster is right on "
        "the day it is printed and wrong the first time bin/ grows a command"
    )

    flags = sorted(set(re.findall(r"--[a-z][a-z-]*", code)))
    assert flags == ["--help", "--list"], (
        f"the printed script names these flags: {flags}. Only the two it ASKS WITH may "
        "appear; a verb's own flags are read from that verb at completion time"
    )

    assert "set -e" not in code, (
        "the printed script sets -e, and it is sourced into an interactive shell: a "
        "non-zero grep would then kill the operator's terminal"
    )
    assert str(REPO_ROOT) in code, (
        "the checkout path is not embedded, so the function would complete against "
        "whatever directory the operator happened to be in"
    )


def test_sourced_in_bash_it_completes_verbs_from_the_list(printed: str, tmp_path: Path) -> None:
    """Every verb `--list` gives, and only those -- including one planted now.

    The planted verb is the proof that the list is read rather than remembered:
    it did not exist when the script was printed, and it still completes.

    **The registration is asserted first, and the battery is why.** Every proof
    here calls `_apg_complete` by hand, the way the driver does -- so dropping
    the `complete -F` line entirely left all of them green while the script did
    nothing whatsoever in a real shell. A function bash never binds to a command
    is a function bash never calls, and only `complete -p` can see the
    difference.
    """
    bound = registrations(printed, tmp_path / "c.sh")
    for name in ("bin/apg.sh", "apg"):
        assert any(line.endswith(f" {name}") for line in bound), (
            f"nothing is registered for {name!r} after sourcing: {bound}. The function is "
            "defined and bound to nothing, which is a script that does nothing"
        )
    assert all("_apg_complete" in line for line in bound), bound

    offered = complete(printed, tmp_path / "c.sh", "apg", "")
    assert sorted(offered) == sorted(verbs()), (
        f"the completion and `--list` disagree: only in completion "
        f"{sorted(set(offered) - set(verbs()))}, only in --list "
        f"{sorted(set(verbs()) - set(offered))}"
    )

    prefixed = complete(printed, tmp_path / "c.sh", "apg", "d")
    assert prefixed, "no verb begins with `d`, which cannot be true"
    assert prefixed == sorted(verb for verb in verbs() if verb.startswith("d"))

    planted = REPO_ROOT / "bin" / "zzz-run2-completion-probe.sh"
    assert not planted.exists(), "the probe name is already taken"
    planted.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n", encoding="utf-8")
    planted.chmod(0o755)
    try:
        after = complete(printed, tmp_path / "c.sh", "apg", "zzz-run2-completion")
        assert after == ["zzz-run2-completion-probe"], (
            f"a command added to bin/ after the script was printed did not complete: {after}. "
            "The roster is baked in"
        )
    finally:
        planted.unlink()

    assert complete(printed, tmp_path / "c.sh", "apg", "zz") == [], (
        "a prefix matching nothing offered something"
    )


def test_it_completes_a_verbs_flags_from_its_help(printed: str, tmp_path: Path) -> None:
    """A verb's flags, read from that verb, and a path left to bash.

    The second half matters as much as the first: a completion function that
    returned an empty `COMPREPLY` for a non-flag word would REPLACE bash's
    default, and the default is a path -- which is what `--project` wants next.
    """
    offered = complete(printed, tmp_path / "c.sh", "apg", "dev", "--")
    help_text = run_apg("dev", "--help").stdout
    from_help = sorted(set(re.findall(r"--[a-z][a-z-]*", help_text)))
    assert offered == from_help, (
        f"the flags offered for `dev` are not the ones its --help names: offered {offered}, "
        f"help {from_help}"
    )
    assert "--project" in offered, "dev's own --help names --project; the completion lost it"

    narrowed = complete(printed, tmp_path / "c.sh", "apg", "dev", "--pro")
    assert narrowed == ["--project"], narrowed

    assert complete(printed, tmp_path / "c.sh", "apg", "dev", "") == [], (
        "a word that is not a flag was answered, which replaces bash's own path completion"
    )
    assert complete(printed, tmp_path / "c.sh", "apg", "no-such-verb", "--") == [], (
        "a verb that does not exist offered flags, so a failing --help is being read as output"
    )


def test_an_unknown_shell_is_refused_with_exit_two() -> None:
    """Exit 2 naming the one that exists, and no half-printed script."""
    for argument in ("zsh", "fish", "--bash"):
        result = run_apg("completion", argument)
        assert result.returncode == 2, (
            f"`completion {argument}` exited {result.returncode}: {result.stderr}"
        )
        assert "bash" in result.stderr, (
            f"the refusal does not name the shell that does exist: {result.stderr}"
        )
        assert "_apg_complete" not in result.stdout, (
            "a refused shell still got part of a completion script"
        )

    bare = run_apg("completion")
    assert bare.returncode == 2
    assert "Usage:" in bare.stderr


def test_the_printed_script_prints_no_environment_value() -> None:
    """D105's neighbourhood: a completion script is sourced, so anything it
    prints lands in the operator's terminal on a keystroke."""
    planted = "APG_CANARY_VALUE_bH3x9Qf2"
    environment = _environment()
    environment["APG_CANARY"] = planted
    result = subprocess.run(
        [str(APG), "completion", "bash"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert planted not in result.stdout + result.stderr

    code = COMPLETION.read_text(encoding="utf-8")
    for dump in ("printenv", "env | ", "set -x", "declare -p"):
        assert dump not in code, f"completion.sh may dump the environment via {dump!r}"
