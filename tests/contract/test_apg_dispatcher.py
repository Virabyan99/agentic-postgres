"""One front door over the commands that already exist (`REL-CLI-001`).

**What this module is mostly about is what the dispatcher must NOT do.** It adds
a name; it must not add a path, a privilege, a second list of verbs, or a change
to any verb's exit code. Each of those is asserted, because each is the natural
way a dispatcher stops being thin.
"""

from __future__ import annotations

import subprocess

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

APG = REPO_ROOT / "bin" / "apg.sh"


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(APG), *arguments], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


def verbs() -> list[str]:
    result = run("--list")
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


# ---------------------------------------------------------------------------
# The verb set is derived, not kept
# ---------------------------------------------------------------------------


def test_every_shell_command_in_bin_is_reachable_as_a_verb() -> None:
    """ADR 0002. The dispatcher holds no list, so this compares it to the disk.

    A dispatcher with its own roster would be a third authority for which
    commands exist -- beside `bin/` and beside `SHELL_COMMANDS` -- and a stale
    third list means a verb that silently stops being reachable.
    """
    on_disk = {path.stem for path in (REPO_ROOT / "bin").glob("*.sh") if path.stem != "apg"}
    listed = set(verbs())
    assert on_disk - listed == set(), f"in bin/ and not reachable: {sorted(on_disk - listed)}"


def test_deploy_is_reachable_although_its_script_is_not_in_bin() -> None:
    """The one named exception, with its reason attached (D694)."""
    assert "deploy" in verbs()
    assert (REPO_ROOT / "deploy.sh").is_file()
    assert not (REPO_ROOT / "bin" / "deploy.sh").exists()


def test_the_dispatcher_does_not_list_itself() -> None:
    assert "apg" not in verbs()


def test_the_list_is_sorted_and_not_empty() -> None:
    """An operator reading it twice must read it the same way twice."""
    listed = verbs()
    assert listed == sorted(listed)
    assert len(listed) > 30, f"only {len(listed)} verbs; the derivation is not reading bin/"


def test_a_command_added_to_bin_becomes_a_verb_with_nothing_edited() -> None:
    """The roster is derived, proved by adding one rather than by reading source.

    The first version of this test scanned the script for verb names and failed
    on its own usage text, which says `apg doctor --verbose` as an example. **A
    text scan standing in for a construct** is D464, and it fails in both
    directions: it flagged prose, and it would have passed a roster spelled in a
    way the scan did not anticipate.

    So the property is exercised instead. A script that exists is a verb; a
    script that does not is not.
    """
    planted = REPO_ROOT / "bin" / "zzz-run5-derivation-probe.sh"
    assert not planted.exists(), "the probe name is already taken"
    planted.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 7\n", encoding="utf-8")
    planted.chmod(0o755)
    try:
        assert "zzz-run5-derivation-probe" in verbs(), (
            "a script added to bin/ did not become a verb; the roster is not derived"
        )
        assert run("zzz-run5-derivation-probe").returncode == 7, (
            "the planted verb ran but its exit code did not reach the caller"
        )
    finally:
        planted.unlink()

    assert "zzz-run5-derivation-probe" not in verbs(), (
        "the verb outlived its script; something is caching the roster"
    )


# ---------------------------------------------------------------------------
# It refuses before it builds a path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hostile",
    [
        "../../etc/passwd",
        "ab../../etc/passwd",
        "a/b",
        "a.b",
        "aB",
        "a;rm",
        "-x",
        "",
    ],
)
def test_a_name_that_is_not_a_verb_is_refused_by_the_pattern(hostile: str) -> None:
    """`ab../../etc/passwd` is the one that matters and it is not hypothetical.

    The first version validated with a `case` glob, and in glob syntax `*`
    matches any string rather than more of the preceding class -- so that input
    passed validation and was stopped only by the file-existence check
    afterwards.

    **And the first version of THIS test could not tell the difference.** It
    asserted only `returncode == 2`, which is what *both* refusals return: the
    pattern's, and "no such verb" from the file check. The battery proved it --
    restoring the glob, and then deleting the check outright, left this green
    (D374: a test that passes for a reason other than the one it names is worse
    than a weak assertion).

    So the message is asserted, not just the code. `is not a verb name` comes
    only from the pattern.
    """
    result = run(hostile)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "is not a verb name" in result.stderr, (
        f"{hostile!r} was refused, but not by the pattern:\n{result.stderr}"
    )
    assert "no such verb" not in result.stderr, (
        f"{hostile!r} reached the file check; the pattern let it through"
    )
    assert "/etc/passwd" not in result.stdout


def test_an_unknown_but_well_formed_verb_is_refused_and_says_where_to_look() -> None:
    result = run("nosuchverb")
    assert result.returncode == 2
    assert "no such verb" in result.stderr
    assert "--list" in result.stderr


# ---------------------------------------------------------------------------
# It is thin
# ---------------------------------------------------------------------------


def test_a_verbs_own_help_is_what_comes_back() -> None:
    """`apg doctor --help` is `bin/doctor.sh --help`, not a summary of it."""
    through = run("doctor", "--help")
    direct = subprocess.run(
        [str(REPO_ROOT / "bin" / "doctor.sh"), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert through.returncode == direct.returncode
    assert through.stdout == direct.stdout


def test_a_verbs_exit_code_reaches_the_caller_unchanged() -> None:
    """`exec` replaces this process, so a verb's exit code is its own.

    `upgrade.sh` with no arguments exits 2. A dispatcher that ran the verb in a
    subshell and returned its own status would break every caller that branches
    on one -- and it would look fine on the happy path.
    """
    through = run("upgrade")
    direct = subprocess.run(
        [str(REPO_ROOT / "bin" / "upgrade.sh")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert direct.returncode == 2, "the fixture verb no longer exits 2; pick another"
    assert through.returncode == direct.returncode


def test_arguments_reach_the_verb_untouched_including_one_with_spaces() -> None:
    """A dispatcher that lost quoting would corrupt exactly the arguments an
    operator is most likely to have quoted deliberately."""
    result = run("upgrade", "plan", "--project", "a b c")
    # The verb echoes the path it derived from the project key, and that path
    # contains `a b c` as ONE component. Three arguments would have produced
    # `.../a/outputs.json` and an "unrecognized arguments" error instead.
    assert "/a b c/outputs.json" in result.stderr, result.stdout + result.stderr
    assert "unrecognized arguments" not in result.stderr


def test_it_uses_exec_so_it_cannot_alter_what_the_verb_does() -> None:
    body = "\n".join(
        line
        for line in APG.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    assert 'exec "${script}" "$@"' in body, "the dispatcher no longer execs the verb"


def test_no_verb_is_wrapped_or_renamed() -> None:
    """Every command keeps its own name and its own file. The dispatcher adds a
    name; it does not move anything."""
    for name in verbs():
        if name == "deploy":
            continue
        assert (REPO_ROOT / "bin" / f"{name}.sh").is_file()


def test_no_arguments_prints_usage_and_refuses() -> None:
    result = run()
    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_help_exits_zero_and_records_why_it_is_not_on_the_path() -> None:
    """The decision is in the help text because it is the operator's question.

    Installing `apg` onto PATH would put a copy outside the release, and a host
    running whichever copy it was provisioned with is ADR 0037's failure: a
    two-session-old launcher deployed a project through the wrong session and
    only then failed.
    """
    result = run("--help")
    assert result.returncode == 0
    assert "not installed onto PATH" in result.stdout
    assert "0037" in result.stdout
