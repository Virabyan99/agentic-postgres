"""One front door over the commands that already exist (`REL-CLI-001`).

**What this module is mostly about is what the dispatcher must NOT do.** It adds
a name; it must not add a path, a privilege, a second list of verbs, or a change
to any verb's exit code. Each of those is asserted, because each is the natural
way a dispatcher stops being thin.
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


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Every proof below the `APG_PROJECT` block runs with the variable ABSENT.

    Session 25 gave the dispatcher one behaviour of its own, read from the
    environment. An operator who has exported `APG_PROJECT` in the shell that
    runs pytest would otherwise be running a different dispatcher from the one
    these proofs describe -- and the proofs that would change are the ones about
    arguments reaching the verb untouched, which is exactly the property the
    variable bends. So the environment is controlled here rather than inherited,
    and the proofs that are ABOUT the variable set it explicitly.
    """
    environment = {key: value for key, value in os.environ.items() if key != "APG_PROJECT"}
    return subprocess.run(
        [str(APG), *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def run_with_default(default: str | Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """The dispatcher with `APG_PROJECT` set to exactly this value."""
    environment = dict(os.environ)
    environment["APG_PROJECT"] = str(default)
    return subprocess.run(
        [str(APG), *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


#: The announcement, as an operator reads it. Asserted verbatim: a default that
#: applies silently is the failure this line exists to prevent, so its wording
#: is part of the contract rather than a detail of the implementation.
def announcement(path: str | Path) -> str:
    return f"apg: --project {path} (from APG_PROJECT)"


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
    operator is most likely to have quoted deliberately.

    **The verb changed from `plan` to `check` because the old one only echoed the
    path by accident** (D876). `plan` refuses with *"--candidate is required"*
    before it derives anything, and that refusal names no path -- so this passed
    only where `check`'s permission-denied message happened to be reachable, and
    went red on a runner where the state root does not exist at all. `check`
    names the derived path in **both** of its answers, so the quoting claim no
    longer rides on a directory this machine has and a fresh one does not.
    """
    result = run("upgrade", "check", "--project", "a b c")
    # The verb echoes the path it derived from the project key, and that path
    # contains `a b c` as ONE component. Three arguments would have produced
    # `.../a/outputs.json` and an "unrecognized arguments" error instead.
    output = result.stdout + result.stderr
    assert "/a b c/outputs.json" in output, output
    assert "unrecognized arguments" not in output


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


# ---------------------------------------------------------------------------
# `DX-CTX-001` -- the one behaviour the dispatcher has of its own (ADR 0207 §2)
# ---------------------------------------------------------------------------

#: A verb whose help documents `--project FILE`: it takes a manifest path.
FILE_VERB = ("dev", "status")

#: A verb whose help documents `--project KEY`: it takes a deployed project's
#: key, so the default must NOT reach it. Handing it a path is not refused --
#: `upgrade check --project project.alpha.yaml` derives a state-root path from
#: the filename and reports on it (D1328). A wrong answer, not an error.
KEY_VERB = ("upgrade", "check")

#: A verb that names no `--project` at all, and exits 0 quickly.
NO_FLAG_VERB = ("lock-versions", "--check")

#: The line-anchored form the dispatcher matches, kept here so the guard below
#: reads the same rule the product reads rather than a paraphrase of it.
DOCUMENTS_A_MANIFEST = re.compile(r"^[ \t]*--project[ \t]+FILE([ \t]|$)", re.MULTILINE)

#: What a parser says when it does not know the flag.
REFUSES_THE_FLAG = re.compile(
    r"unrecognized arguments[^\n]*--project(?![-a-z])|unknown option[^\n]*--project(?![-a-z])",
    re.IGNORECASE,
)

#: A flag no command can accept, so the probe below always ends in a parser.
CANARY_FLAG = "--zzz-apg-dispatcher-probe"


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    """A readable file for `APG_PROJECT`. It need not be a valid manifest.

    What is under test is whether the dispatcher appends the path, and the verb
    naming the path back is the observation. A VALID manifest would make `dev
    status` reach Docker, which is a different test's subject and a slower one.
    """
    path = tmp_path / "default-project.yaml"
    path.write_text("schema_version: 5\n", encoding="utf-8")
    return path


def test_the_default_project_is_applied_only_to_a_verb_whose_help_names_the_flag(
    manifest: Path,
) -> None:
    """Three verbs, three answers, and the middle one is the point.

    A verb that documents `--project FILE` receives the default. A verb that
    documents `--project KEY` does not, because the value would be wrong rather
    than refused. A verb that documents neither does not, because appending a
    flag it does not take would break a command that worked -- which is what
    `dr-kit verify` would have suffered, and D1316 is the measurement.
    """
    applied = run_with_default(manifest, *FILE_VERB)
    assert announcement(manifest) in applied.stderr, (
        f"a verb documenting `--project FILE` did not receive the default: {applied.stderr}"
    )
    assert str(manifest) in applied.stdout + applied.stderr, (
        "the default was announced but the verb never saw the path"
    )

    by_key = run_with_default(manifest, *KEY_VERB)
    assert announcement(manifest) not in by_key.stderr, (
        "a verb documenting `--project KEY` takes a project key, not a path, and received "
        f"the default anyway: {by_key.stderr}"
    )

    no_flag = run_with_default(manifest, *NO_FLAG_VERB)
    assert announcement(manifest) not in no_flag.stderr, (
        f"a verb that names no --project received one: {no_flag.stderr}"
    )
    assert no_flag.returncode == 0, (
        f"the verb that should have been left alone did not run cleanly: {no_flag.stderr}"
    )


def test_an_explicit_project_wins_over_the_default_and_nothing_is_printed(
    manifest: Path, tmp_path: Path
) -> None:
    """Both spellings, because recognising one would append a second flag.

    The verbs measured refuse `--project=FILE` and accept `--project FILE`, so
    the `=` form is not a spelling this product supports. It is still an
    operator saying which project they meant, and the right answer to it is the
    verb's own error rather than a duplicate flag on top of it (D1318).
    """
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text("schema_version: 5\n", encoding="utf-8")

    for argument in (f"--project={explicit}", None):
        arguments = [*FILE_VERB, argument] if argument else [*FILE_VERB, "--project", str(explicit)]
        result = run_with_default(manifest, *arguments)
        assert "from APG_PROJECT" not in result.stderr, (
            f"the default was applied over an explicit {arguments[-2:]}: {result.stderr}"
        )
        assert str(manifest) not in result.stdout + result.stderr, (
            f"the default's path reached a verb that was given one: {result.stderr}"
        )


def test_the_default_is_announced_on_stderr_each_time_it_is_applied(
    manifest: Path,
) -> None:
    """On stderr, once, verbatim -- and never on stdout.

    stdout is what a caller pipes. A dispatcher that wrote a sentence of its own
    into a verb's output stream would corrupt exactly the invocations an
    operator built a pipeline around, and `apg mcp-contract compile > FILE` is
    one of them in README.
    """
    result = run_with_default(manifest, *FILE_VERB)
    assert result.stderr.count(announcement(manifest)) == 1, (
        f"expected exactly one announcement, got: {result.stderr}"
    )
    assert "from APG_PROJECT" not in result.stdout, (
        f"the announcement reached stdout, which a caller pipes: {result.stdout}"
    )

    twice = run_with_default(manifest, *FILE_VERB)
    assert twice.stderr.count(announcement(manifest)) == 1, (
        "the announcement is per invocation; a second run printed a different number"
    )


def test_an_unreadable_default_is_refused_before_exec(tmp_path: Path) -> None:
    """Exit 2, and the verb never runs.

    After `exec` this process is gone, so a verb handed an unreadable path would
    report a missing manifest the operator never typed -- naming a file they did
    not choose, from a variable they may have forgotten they exported.
    """
    missing = tmp_path / "not-here.yaml"
    result = run_with_default(missing, *FILE_VERB)

    assert result.returncode == 2, (
        f"an unreadable APG_PROJECT exited {result.returncode}, not 2: {result.stderr}"
    )
    assert "APG_PROJECT" in result.stderr and str(missing) in result.stderr
    assert not result.stderr.startswith("dev:") and "dev:" not in result.stderr, (
        f"the verb ran before the default was checked: {result.stderr}"
    )

    unreadable = tmp_path / "locked.yaml"
    unreadable.write_text("schema_version: 5\n", encoding="utf-8")
    unreadable.chmod(0o000)
    try:
        denied = run_with_default(unreadable, *FILE_VERB)
    finally:
        unreadable.chmod(0o644)
    if os.geteuid() == 0:
        # Root reads through 0000, so there is no unreadable file to observe
        # and the branch cannot be entered. Not a skip: the assertion above
        # already proved the branch on a path that does not exist at all.
        assert denied.returncode in {2, 5}, denied.stderr
    else:
        assert denied.returncode == 2, (
            f"a file this user cannot read exited {denied.returncode}: {denied.stderr}"
        )


def test_the_default_never_reaches_help_or_list(manifest: Path) -> None:
    """`--help`, `-h` and `--list`, at both levels.

    A help request that grew a flag would print a sentence about a file the
    reader never mentioned, in the one output whose job is to tell them what the
    command takes.
    """
    for arguments in (("--list",), ("dev", "--help"), ("dev", "-h"), ("--help",)):
        result = run_with_default(manifest, *arguments)
        assert "from APG_PROJECT" not in result.stderr, (
            f"apg {' '.join(arguments)} was rewritten: {result.stderr}"
        )
        assert result.returncode == 0, f"apg {' '.join(arguments)}: {result.stderr}"

    # The dispatcher's own --help DOCUMENTS the announcement's wording, so it
    # says the words on stdout by design. That is the page describing the
    # behaviour, not the behaviour happening.
    own_help = run_with_default(manifest, "--help")
    assert "APG_PROJECT" in own_help.stdout, "the usage no longer documents the variable"
    assert str(manifest) not in own_help.stdout + own_help.stderr, (
        "the usage printed the operator's actual value, which is not a usage's business"
    )


def test_the_dispatcher_still_keeps_no_list_of_verbs(manifest: Path) -> None:
    """ADR 0002, re-asserted after the dispatcher grew a behaviour of its own.

    The natural way to implement a default is a list of the verbs that take the
    flag. That list is the second authority this file's header refuses, and it
    goes stale the first time a verb grows `--project`.

    **Exercised, not scanned.** The first version of this read the source for
    verb names and failed on the dispatcher's own usage text, which says `apg
    doctor --verbose` as an example and now `apg dev up` as another -- D464
    exactly, the mistake the module records two tests above, and it fails in
    both directions: it flags prose, and it would pass a list spelled in a way
    the scan did not anticipate.

    So two scripts are planted that no list could contain, one documenting
    `--project FILE` and one documenting nothing, and the default is observed
    reaching the first and not the second. A verb invented thirty seconds ago
    receiving the default is proof that the set was derived.
    """
    takes = REPO_ROOT / "bin" / "zzz-run2-takes-a-manifest.sh"
    plain = REPO_ROOT / "bin" / "zzz-run2-takes-nothing.sh"
    assert not takes.exists() and not plain.exists(), "a probe name is already taken"

    takes.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [ "${1:-}" = "--help" ]; then\n'
        "  printf '%s\\n' 'Usage: probe --project FILE'\n"
        "  printf '%s\\n' '  --project FILE   the manifest'\n"
        "  exit 0\n"
        "fi\n"
        'printf "probe saw: %s\\n" "$*"\n',
        encoding="utf-8",
    )
    plain.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [ "${1:-}" = "--help" ]; then\n'
        "  printf '%s\\n' 'Usage: probe [--verbose]'\n"
        "  exit 0\n"
        "fi\n"
        'printf "probe saw: %s\\n" "$*"\n',
        encoding="utf-8",
    )
    takes.chmod(0o755)
    plain.chmod(0o755)
    try:
        applied = run_with_default(manifest, "zzz-run2-takes-a-manifest", "go")
        assert announcement(manifest) in applied.stderr, (
            "a verb planted seconds ago, documenting `--project FILE`, did not receive the "
            f"default -- so the set of verbs that take it is kept somewhere: {applied.stderr}"
        )
        assert applied.stdout.strip() == f"probe saw: go --project {manifest}", (
            f"the default was appended in the wrong place or shape: {applied.stdout!r}"
        )

        left_alone = run_with_default(manifest, "zzz-run2-takes-nothing", "go")
        assert "from APG_PROJECT" not in left_alone.stderr, (
            f"a verb documenting no --project received one: {left_alone.stderr}"
        )
        assert left_alone.stdout.strip() == "probe saw: go", (
            f"a verb that takes no manifest had its arguments rewritten: {left_alone.stdout!r}"
        )
    finally:
        takes.unlink()
        plain.unlink()

    code = "\n".join(
        line
        for line in APG.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    assert 'exec "${script}" "$@"' in code, (
        "the unmodified exec path is gone; every invocation now goes through the branch "
        "that appends"
    )


def test_every_verb_whose_help_documents_the_flag_actually_accepts_it() -> None:
    """The guard the `dr-kit` fix is not (D1316).

    Rewriting one usage block fixes one verb. What stops the next one is this:
    the derivation reads a verb's help, so a verb whose PROSE outruns its PARSER
    would be handed a flag it refuses, and the operator would find out instead
    of a test. `dr-kit verify` was that verb, and it was found by hand.

    Each verb is probed with the flag AND with a flag nothing can accept, so the
    run always ends in the parser before any effect. Three outcomes, ADR 0195:
    accepts, refuses, and *could not be determined* -- the last for a command
    that stops at a root check before it parses anything, which is reported
    rather than counted as a pass.

    Goes red if: a verb documents `--project FILE` and its parser does not take
    `--project`.
    """
    accepted: list[str] = []
    refused: list[str] = []
    undetermined: list[str] = []

    for verb in verbs():
        script = REPO_ROOT / "deploy.sh" if verb == "deploy" else REPO_ROOT / "bin" / f"{verb}.sh"
        help_text = subprocess.run(
            [str(script), "--help"], capture_output=True, text=True, check=False
        ).stdout
        if not DOCUMENTS_A_MANIFEST.search(help_text):
            continue

        for prefix in _subcommands(help_text, verb) or [None]:
            arguments = [*([prefix] if prefix else []), "--project", "/nonexistent", CANARY_FLAG]
            name = f"{verb} {prefix}" if prefix else verb
            probe = subprocess.run(
                [str(script), *arguments],
                capture_output=True,
                text=True,
                check=False,
                cwd=REPO_ROOT,
                timeout=60,
            )
            blob = probe.stdout + probe.stderr
            if re.search(r"needs root|requires root|must be run as root", blob, re.IGNORECASE):
                undetermined.append(f"{name} (stops at a root check)")
            elif REFUSES_THE_FLAG.search(blob):
                refused.append(f"{name}: {blob.strip().splitlines()[-1][:120]}")
            else:
                accepted.append(name)

    assert not refused, (
        "these document `--project FILE` and their parser refuses it, so the dispatcher's "
        f"default would break them: {refused}. Correct the usage text, as dr-kit's was "
        "(D1316) -- never add an exemption list"
    )
    assert len(accepted) >= 8, (
        f"only {len(accepted)} verbs were probed conclusively ({undetermined} could not be), "
        "so this comparison is close to vacuous. Read why before trusting a green"
    )


def _subcommands(help_text: str, verb: str) -> list[str]:
    """Bare words that follow the script's name on a Usage line."""
    found: list[str] = []
    stem = f"{verb}.sh"
    for line in help_text.splitlines():
        if stem not in line:
            continue
        tail = line.split(stem, 1)[1].strip()
        if not tail:
            continue
        for word in tail.split()[0].split("|"):
            if re.fullmatch(r"[a-z][a-z0-9-]*", word) and word not in found:
                found.append(word)
    return found
