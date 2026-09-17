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
import re
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

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
    # Session 21 (ADR 0201, D1137): one verb, `init`, scaffolding a project's
    # capability entry from the merged reviewed surface. Listed here the run it
    # landed (D1014).
    "bin/agent.sh",
    "bin/apg.sh",
    "bin/apg-diag.sh",
    "bin/api.sh",
    "bin/api-contract.sh",
    "bin/app-contract.sh",
    "bin/auth-admin.sh",
    "bin/backup.sh",
    "bin/bootstrap-providers.sh",
    # Session 25 (ADR 0207 §2): prints a bash completion script and installs
    # nothing. Listed here the run it landed (D1014), and `git add`ed before
    # this module runs, because `test_commands_are_executable_in_the_git_index`
    # reads the INDEX's mode and not the working tree's (D1188).
    "bin/completion.sh",
    "bin/compose.sh",
    "bin/connect.sh",
    "bin/docker-firewall.sh",
    "bin/doctor.sh",
    "bin/edge.sh",
    "bin/edge-network.sh",
    "bin/fleet.sh",
    # Session 23 (ADR 0204, D1222): the generator. Listed here the run it landed
    # (D1014) -- and `git add`ed before this module runs, because
    # `test_commands_are_executable_in_the_git_index` reads the INDEX's mode and
    # not the working tree's (D1188).
    "bin/generate.sh",
    "bin/lock-dev-deps.sh",
    "bin/lock-versions.sh",
    "bin/materialize-secrets.sh",
    "bin/mcp-contract.sh",
    "bin/database-access.sh",
    "bin/database-ports.sh",
    "bin/db.sh",
    # Session 22 (ADR 0203): the disposable local cluster. Listed here the
    # run it landed (D1014) -- a command in bin/ and in neither list is a
    # command none of this module's checks apply to, including the
    # secret-argument scan.
    "bin/dev.sh",
    "bin/dev-token.sh",
    "bin/dr-kit.sh",
    # Session 25 (ADR 0207 §3): the walker reads their own record the way the
    # sweep will. Listed the run it landed (D1014), `git add`ed first (D1188).
    "bin/dx-record.sh",
    "bin/docs.sh",
    "bin/migrate.sh",
    "bin/postgres-bootstrap.sh",
    "bin/project-retire.sh",
    "bin/project-runtime.sh",
    "bin/provision-host.sh",
    "bin/rehearse.sh",
    # Session 28 (ADR 0214): the reading taken before a tag is cut. Listed here
    # the run it landed and `git add`ed before this module runs, because
    # `test_commands_are_executable_in_the_git_index` reads the INDEX's mode and
    # not the working tree's (D1014, D1188).
    "bin/release-reading.sh",
    "bin/restore.sh",
    "bin/restore-test.sh",
    "bin/rotate-secret.sh",
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
    "bin/session-10-check.sh",
    "bin/session-11-check.sh",
    "bin/session-12-check.sh",
    "bin/session-13-check.sh",
    "bin/session-14-check.sh",
    "bin/session-15-check.sh",
    "bin/session-16-check.sh",
    "bin/session-17-check.sh",
    "bin/session-18-check.sh",
    # Session 20. Derived from 18s by diff (D505, D507, D678, D693, D703);
    # its five declaration flags are removed, because every live half this
    # session adds reads a roster variable the gate already exports.
    "bin/session-20-check.sh",
    # Session 21. Derived from 20's by diff; Session 18's five declaration
    # flags are back (D1133): a gate carries every declaration a proof it RUNS
    # can read, and claims_through_session(21) runs Session 18's.
    "bin/session-21-check.sh",
    # Session 22. Derived from 21's by diff, and the first gate whose OFFLINE
    # mode writes an evidence half (ADR 0202): four of this session's claims
    # are about a command a developer runs on their own machine. It is also the
    # first offline mode that requires docker, and says so as a prerequisite
    # rather than letting the cluster proofs skip into a `not_run` claim.
    "bin/session-22-check.sh",
    # Session 23. Derived from 22's by diff. Its offline mode writes a half
    # too, and the two claims it reports are about a GENERATED ARTEFACT and
    # its generator -- settled by four committed files and a container. The
    # two that need a deployment are separate host claims rather than folded
    # in, which is the line ADR 0202 exists to let a session draw.
    "bin/session-23-check.sh",
    "bin/session-24-check.sh",
    # Session 25 (ADR 0207). Derived from 24's by diff. Its offline mode
    # writes a half reporting THREE claims -- one more than any session has
    # declared offline -- and its host mode answers for this session alone,
    # because Session 24's trip paid 22, 23 and 24 from one sweep (D1244).
    "bin/session-25-check.sh",
    "bin/smoke-test.sh",
    # Session 24 (ADR 0205). A loopback client of a deployment's own
    # surfaces, holding the human's token in one process and handing the
    # browser a launch cookie instead. Listed here the run it landed
    # (D1014), and `git add`ed before this file was run (D1188).
    "bin/storage-admin.sh",
    "bin/studio.sh",
    "bin/upgrade.sh",
)

PYTHON_COMMANDS = (
    "bin/agent.py",
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
    "bin/dev.py",
    "bin/dev-token.py",
    "bin/docs.py",
    "bin/doctor.py",
    "bin/dr-kit.py",
    # Session 25 (ADR 0207 §3): the five readings that decide DX-001, run by
    # the walker as well as by the sweep. Listed the run it landed (D1014).
    "bin/dx-record.py",
    "bin/fleet.py",
    "bin/generate.py",
    "bin/materialize-secrets.py",
    "bin/mcp-contract.py",
    "bin/migrate.py",
    "bin/postgres-bootstrap.py",
    "bin/project-retire.py",
    "bin/render-acceptance-matrix.py",
    "bin/render-capacity-envelope.py",
    "bin/render-evaluation-report.py",
    "bin/render-mcp-catalog.py",
    "bin/render-config.py",
    "bin/render-jwks.py",
    "bin/render-mount-digests.py",
    "bin/render-secret-override.py",
    "bin/rehearse.py",
    # Session 20, ADR 0199. The one place a rendered document's path is
    # resolved and its absence interpreted, so that `[ -f ]` -- which answers
    # false both for a missing file and for one this user cannot traverse to --
    # is not asked the question in three shells that each decided for themselves
    # what the answer meant (D1060).
    "bin/rendered-document.py",
    # Session 28 (ADR 0214). It runs `git` and nothing else, and it is the half
    # that measures; every conclusion is in `agentic_postgres.release_reading`.
    "bin/release-reading.py",
    "bin/restore.py",
    "bin/restore-test.py",
    "bin/rotate-secret.py",
    "bin/rotate-signing-key.py",
    "bin/storage-admin.py",
    "bin/studio.py",
    "bin/upgrade.py",
    "bin/write-session-evidence.py",
)

#: Commands that document a future capability and refuse to pretend otherwise.
#:
#: **Empty since Session 10 Run 8, and the lifecycle is over.** Four commands
#: passed through here, each leaving in the run that implemented it:
#: ``bin/bootstrap-providers.sh`` in Session 2, ``bin/migrate.sh`` in Session 3,
#: ``bin/connect.sh`` in Session 4 and ``bin/restore-test.sh`` in Session 10
#: (D524, ADR 0017, ADR 0151).
#:
#: Emptying this tuple was never a way to make ``test_future_stub_exits_ten``
#: pass, which is the whole reason ADR 0017 exists -- so that test is **gone**,
#: and what replaced it asserts more than it did:
#:
#: * ``test_a_graduated_stub_reports_missing_input_not_absence`` drives all four
#:   graduates and requires exit ``2`` from each. The old test drove whatever was
#:   still listed here and required exit ``10``.
#: * ``test_no_command_reports_an_unavailable_capability`` drives **every**
#:   command in :data:`SHELL_COMMANDS` and requires that none of them returns
#:   ``10``. Forty commands rather than one, and it is the node id ``DX-002``
#:   now names.
#: * ``test_the_stub_lifecycle_is_complete`` guards the guard: this tuple is
#:   empty **and** the graduate list is exactly the four, so a fifth stub added
#:   later cannot quietly skip the lifecycle.
#:
#: Measured before it was asserted: no command in ``SHELL_COMMANDS`` returns 10
#: on a bare invocation. `bin/session-01-check.sh` and `bin/smoke-test.sh` return
#: 1, `bin/apg-diag.sh` and `bin/doctor.sh` return 0, and everything else
#: returns 2.
FUTURE_STUBS: tuple[str, ...] = ()

#: The four commands that were stubs and are not (ADR 0017's whole lifecycle).
#:
#: Listed so that the assertions which replaced ``test_future_stub_exits_ten``
#: have something to drive. A bare invocation of each is *missing input*, which
#: is ``2``; a ``10`` from any of them means a command went back to being a stub.
GRADUATED_STUBS: tuple[str, ...] = (
    "bin/bootstrap-providers.sh",
    "bin/migrate.sh",
    "bin/connect.sh",
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


#: Commands whose `--help` documents at least one VERB, derived from the text
#: rather than listed. Named only as the control for the derivation below: if
#: the regex ever stops matching, every parametrised case passes over an empty
#: verb list and the whole guard goes quiet (§7 question 1).
COMMANDS_WITH_VERBS = {
    "bin/agent.sh",
    "bin/apg.sh",
    "bin/connect.sh",
    "bin/database-access.sh",
    "bin/database-ports.sh",
    "bin/dev.sh",
    "bin/dr-kit.sh",
    "bin/mcp-contract.sh",
    "bin/rehearse.sh",
    "bin/upgrade.sh",
}


def verbs_documented_by(relative: str, help_text: str) -> tuple[str, ...]:
    """The verbs a command's own `--help` documents, read out of that text.

    **Derived, not listed** -- D1316's repair uses the same shape to find which
    verbs take `--project`, and for the same reason: a hand-kept list stops
    covering the directory the first time somebody forgets, and says nothing
    when it does.

    A verb is a lowercase word following the command's own name on a usage
    line. The separator class is spaces and tabs and never the whitespace
    shorthand, which matches a NEWLINE too: with it, a usage block whose lines
    each begin with the command name derives the next line's first word as a
    verb of this one. Measured while writing this -- it read `bin` out of
    `bin/rotate-secret.sh`.
    """
    name = re.escape(Path(relative).name)
    pattern = re.compile(
        rf"^[ \t]*(?:Usage:[ \t]*)?(?:sudo[ \t]+)?(?:\./|bin/)?{name}[ \t]+"
        r"([a-z][a-z0-9-]*)(?![\w/-])",
        re.MULTILINE,
    )
    seen: list[str] = []
    for verb in pattern.findall(help_text):
        if verb not in seen:
            seen.append(verb)
    return tuple(seen)


@pytest.mark.parametrize(
    "relative",
    [command for command in SHELL_COMMANDS if command != "bin/session-01-check.sh"],
)
def test_a_verbs_help_is_a_read_and_needs_nothing(relative: str) -> None:
    """**DX-002**, one level down: a VERB documents itself too (D1395, D1402, D1405).

    `test_help_exits_zero_and_says_something` asks this of the command. Nobody
    asked it of a verb, and **seven verbs in three commands refused**, each for
    a reason that has nothing to do with reading:

    * `bin/dr-kit.sh export --help` exited 3 for want of ROOT;
    * `bin/database-ports.sh allocate|verify|release --help` exited 3, the same;
    * `bin/upgrade.sh check|plan|verify --help` exited 2, because the Python
      side is built with `add_help=False` over a required `--project`, so the
      wrapper dispatched the verb and argparse refused the missing argument
      before it ever considered the flag.

    Three commands, two unrelated causes, one shape: **a wrapper that
    dispatches the verb before it considers `--help`**. Guarded as the class
    rather than as the three instances (D1199's shape), over verbs derived from
    each command's own usage -- so a command that grows a verb tomorrow is
    covered tomorrow, with nobody editing a list.
    """
    top = run(str(REPO_ROOT / relative), "--help")
    verbs = verbs_documented_by(relative, top.stdout)
    if relative in COMMANDS_WITH_VERBS:
        assert verbs, (
            f"{relative} documents verbs and none were derived from its --help; the "
            "derivation is broken, and every other case in this parametrisation is "
            "passing over an empty list"
        )
    for verb in verbs:
        result = run(str(REPO_ROOT / relative), verb, "--help")
        assert result.returncode == 0, (
            f"`{relative} {verb} --help` exited {result.returncode}. A verb's help is a "
            f"READ: it takes no root, no required argument and no host. {result.stderr[:300]}"
        )
        assert len(result.stdout.strip()) > 40, (
            f"`{relative} {verb} --help` exited 0 and printed nothing worth reading"
        )


def test_every_command_documenting_verbs_is_named_in_the_control() -> None:
    """The control's other direction, so it cannot rot into a shorter list.

    `COMMANDS_WITH_VERBS` exists to prove the derivation still derives. A name
    dropped from it weakens the guard silently; a command that GROWS verbs and
    is not added to it weakens it the same way. Both are failures here.
    """
    documenting = {
        relative
        for relative in SHELL_COMMANDS
        if relative != "bin/session-01-check.sh"
        and verbs_documented_by(relative, run(str(REPO_ROOT / relative), "--help").stdout)
    }
    assert documenting == COMMANDS_WITH_VERBS, (
        "COMMANDS_WITH_VERBS disagrees with what the commands' own --help texts "
        f"document. Only in the list: {sorted(COMMANDS_WITH_VERBS - documenting)}; "
        f"only in the tree: {sorted(documenting - COMMANDS_WITH_VERBS)}"
    )


def test_upgrade_usage_names_every_flag_and_class_its_parser_accepts() -> None:
    """**D1381**, and the reason it is scoped to one command.

    `bin/upgrade.sh --help` documented four options and the parser accepted
    five: `--also`, which D743 makes an **operator declaration** rather than a
    convenience, was absent from the page an operator reads to find out what
    they may declare. A flag nobody can find is a flag nobody uses, and this
    one is the only way to tell the planner about a migration -- the class that
    makes a bump irreversible by image rollback.

    Scoped to `bin/upgrade.sh`. A sweep over every parser in `bin/` is a
    measurement nobody has made and is priced in the plan's §10; asserting it
    here would either be red on a dozen commands or quietly narrowed to nothing.

    The eight class names are read from `DECLARABLE` and not typed here, for a
    measured reason: **the first draft of the usage block invented four of
    them**, and was caught by writing this proof rather than by reading it.
    """
    source = (REPO_ROOT / "bin" / "upgrade.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    flags = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and node.args[0].value.startswith("--")
    }
    assert flags, "no --flags were read from bin/upgrade.py; this proof reads them by shape"

    declarable: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "DECLARABLE" for target in node.targets
        ):
            declarable = {
                element.value
                for element in ast.walk(node.value)
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
    assert len(declarable) == 8, f"DECLARABLE carries {len(declarable)} classes, expected 8"

    usage = run(str(REPO_ROOT / "bin" / "upgrade.sh"), "--help")
    assert usage.returncode == 0, usage.stderr

    missing_flags = sorted(flag for flag in flags if flag not in usage.stdout)
    assert not missing_flags, (
        f"bin/upgrade.py accepts {missing_flags} and bin/upgrade.sh --help does not name "
        "them, so an operator cannot find a flag the command takes"
    )

    missing_classes = sorted(name for name in declarable if name not in usage.stdout)
    assert not missing_classes, (
        f"--also accepts {missing_classes} and the usage does not name them. The list an "
        "operator reads must be the list argparse enforces, or `--also` refuses a class "
        "the help text offered"
    )


def test_deploy_help_names_the_session_this_release_implements() -> None:
    """**D1397.** The one argument on that page with no documented origin.

    `--through-session N` takes `CURRENT_SESSION`. It is not in `VERSION`, no
    `--help` in the 4,478-line capture printed it, and `deploy.sh` accepts any
    number BELOW it silently (D59) -- so an operator who guesses low gets exit
    0 and a partial release. The number is derived from the same function the
    deploy itself uses, never typed into the text.
    """
    from agentic_postgres import CURRENT_SESSION

    result = run(str(REPO_ROOT / "deploy.sh"), "--help")
    assert result.returncode == 0, result.stderr
    assert str(CURRENT_SESSION) in result.stdout, (
        f"deploy.sh --help does not name session {CURRENT_SESSION}, so the one "
        "argument whose wrong value is accepted silently still has no documented "
        "source"
    )
    assert "CURRENT_SESSION" in result.stdout, (
        "the number is printed and its source is not, so an operator upgrading to a "
        "release the guide's table does not list has nowhere to read it"
    )


def test_a_command_about_to_refuse_prints_no_success_sentence() -> None:
    """**D1403.** Two commands printed a success line and then refused.

    `bin/migrate.sh --project <manifest with no set> verify-lock` printed
    *"the released lock agrees with the manifest and templates"* -- true -- and
    exited 5. `bin/mcp-contract.sh check --project <refused manifest>` printed
    the whole approved contract and exited 5. ADR 0195's family from the other
    end: not an unknown reported as an answer, but the right answer reported
    when the answer to the question asked is a refusal.

    **The first version of this asserted the wrong thing and could not fail.**
    It took the last line of `stdout + stderr` -- and in that concatenation
    stderr is always last, so a refusal on stderr satisfied it whatever stdout
    said. The battery caught it: the mutation that puts the success sentence
    back BEFORE the refusing call survived.

    "Last on the terminal" is not a property a proof can read through a pipe
    anyway: the interleaving an operator sees depends on which stream is a tty
    and how Python buffers it. What is checkable is stronger and is the thing
    that actually matters -- **a command that is going to refuse writes no
    success sentence to stdout at all.** Then the ordering is true on a
    terminal, in a pipe, and in a log.

    The controls are in the same test: the same two verbs on a VALID project
    must still print their sentences and exit 0. A repair that deleted the
    sentences would satisfy the first half by taking a true report away.
    """
    manifest = REPO_ROOT / "project.example.yaml"
    document = yaml.safe_load(manifest.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as directory:
        # No `migrations.set`: schema 4's shape, which `verify-lock --project`
        # refuses by name. The key is REMOVED rather than emptied -- `set` is
        # required under `migrations`, so leaving a null parent makes the
        # manifest invalid and every command refuses on schema validation
        # instead, which is a different arm.
        setless = dict(document)
        setless["schema_version"] = 4
        setless.pop("migrations", None)
        setless.get("mcp", {}).pop("capabilities", None)
        setless_path = Path(directory) / "setless.yaml"
        setless_path.write_text(yaml.safe_dump(setless, sort_keys=False), encoding="utf-8")

        refused = dict(document)
        refused["a_key_no_schema_allows"] = True
        refused_path = Path(directory) / "refused.yaml"
        refused_path.write_text(yaml.safe_dump(refused, sort_keys=False), encoding="utf-8")

        for command, arguments, path in (
            ("bin/migrate.sh", ("verify-lock",), setless_path),
            ("bin/mcp-contract.sh", ("check",), refused_path),
        ):
            if command == "bin/migrate.sh":
                result = run(str(REPO_ROOT / command), "--project", str(path), *arguments)
            else:
                result = run(str(REPO_ROOT / command), *arguments, "--project", str(path))
            assert result.returncode != 0, (
                f"`{command}` was expected to refuse {path.name} and exited 0; this "
                "proof is no longer exercising the arm it was written for"
            )
            claimed = [
                marker
                for marker in ("agrees with", "compiles to the approved contract")
                if marker in result.stdout
            ]
            assert not claimed, (
                f"`{command}` exited {result.returncode} after writing {claimed} to "
                f"stdout. A sentence already on the terminal cannot be taken back, so "
                "a command that is going to refuse does not print one (D1403). stdout "
                f"was:\n{result.stdout}"
            )

    # The controls: the same two verbs on the release's own project still say
    # so, and still exit 0.
    agreeing = run(str(REPO_ROOT / "bin" / "migrate.sh"), "--project", str(manifest), "verify-lock")
    assert agreeing.returncode == 0, agreeing.stdout + agreeing.stderr
    assert "the released lock agrees" in agreeing.stdout, (
        "the release half's sentence was deleted rather than moved, which satisfies "
        "the ordering rule by taking a true report away"
    )
    assert "agrees with its own lock" in agreeing.stdout, agreeing.stdout

    compiling = run(str(REPO_ROOT / "bin" / "mcp-contract.sh"), "check", "--project", str(manifest))
    assert compiling.returncode == 0, compiling.stdout + compiling.stderr
    assert "compiles to the approved contract" in compiling.stdout, compiling.stdout


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


def test_restore_test_is_no_longer_a_stub() -> None:
    """ADR 0017, fourth and final application (D524, ADR 0151).

    A bare invocation used to be exit ``10``, "unavailable this session". It is
    now a missing required input, which is ``2``. Stated directly, as it is for
    the other three, so that emptying ``FUTURE_STUBS`` without implementing the
    command fails here rather than passing quietly.
    """
    result = run(str(REPO_ROOT / "bin" / "restore-test.sh"))
    assert result.returncode == 2, (
        f"expected 2 (missing required input), got {result.returncode}. "
        "A 10 here means the command went back to being a stub."
    )
    assert "required" in result.stderr.lower()


def test_the_stub_lifecycle_is_complete() -> None:
    """Guard the guard, now that the tuple is empty (ADR 0017, ADR 0151).

    ``test_the_remaining_stubs_are_the_ones_later_sessions_own`` asserted that
    ``FUTURE_STUBS`` held exactly the one command a later session owned. There is
    no later session to own one, so what replaces it says more: the tuple is
    empty **and** the graduate list is exactly the four commands that passed
    through it. A fifth stub added later has to appear in one of the two, and a
    graduate quietly dropped from the second stops being driven by the test
    below -- which is the failure this guard exists to catch.
    """
    assert FUTURE_STUBS == (), (
        f"FUTURE_STUBS is not empty: {FUTURE_STUBS}. A new stub is legitimate, and it "
        "needs its own entry in ADR 0017's lifecycle before it is listed here."
    )
    assert set(GRADUATED_STUBS) == {
        "bin/bootstrap-providers.sh",
        "bin/migrate.sh",
        "bin/connect.sh",
        "bin/restore-test.sh",
    }
    for relative in GRADUATED_STUBS:
        assert relative in SHELL_COMMANDS, f"{relative} graduated out of the command list"


@pytest.mark.parametrize("relative", GRADUATED_STUBS)
def test_a_graduated_stub_reports_missing_input_not_absence(relative: str) -> None:
    """Every graduate, driven: a bare invocation is 2, and it is never 10.

    This is half of what replaced ``test_future_stub_exits_ten``. That test drove
    whatever was still listed in ``FUTURE_STUBS`` -- one command by Session 4 --
    and required ``10``. This drives all four and requires ``2``, which is the
    assertion the three individual ``*_is_no_longer_a_stub`` tests each make for
    one command, made for the set so that a fifth graduate cannot arrive without
    one.
    """
    result = run(str(REPO_ROOT / relative))
    assert result.returncode == 2, (
        f"{relative} returned {result.returncode}, expected 2 (missing required input). "
        "A 10 here means the command went back to being a stub."
    )


#: Commands that DO WORK when invoked with no arguments, so a bare invocation of
#: them is not a question about the exit-code convention -- it is a job.
#:
#: **This set exists because omitting it made the gate recursive** (D584).
#: `bin/smoke-test.sh` with no arguments runs
#: `pytest -q -m "contract and not future"` -- the entire contract suite, which
#: is the suite this module is part of. So the first version of the test below
#: ran the whole contract suite from inside the whole contract suite, on every
#: gate, and the gate went from roughly five minutes to over forty-five.
#:
#: It is an **allowlist of commands that run**, named individually with the
#: reason, rather than a timeout that would merely cap the damage: a bound would
#: have left a nested pytest starting on every gate run and being killed, which
#: is a slow test whose slowness nobody could explain.
#:
#: Each was measured, not assumed (`/tmp/diag/bare.sh`): 120s+ for
#: `smoke-test.sh`, 4.0s for `session-01-check.sh`, and under 0.5s for every
#: other command in `SHELL_COMMANDS`.
COMMANDS_THAT_RUN_WITHOUT_ARGUMENTS: tuple[str, ...] = (
    # Runs the active contract suite. Recursive from here (D584).
    "bin/smoke-test.sh",
    # Renders both fixtures and reports; 4s, and it is a gate.
    "bin/session-01-check.sh",
    # Both print a report and exit 0 with no arguments, by design.
    "bin/doctor.sh",
    "bin/apg-diag.sh",
)


@pytest.mark.parametrize(
    "relative",
    [name for name in SHELL_COMMANDS if name not in COMMANDS_THAT_RUN_WITHOUT_ARGUMENTS],
)
def test_no_command_reports_an_unavailable_capability(relative: str) -> None:
    """Nothing in this repository still refuses a capability it does not have.

    The other half of what replaced ``test_future_stub_exits_ten``, and the node
    id ``DX-002`` now names. The old test asserted that **one** listed command
    returned ``10``; this asserts that **none** of the thirty-six that refuse
    does, which is the property ADR 0017's lifecycle was always working towards
    and which nothing stated until the lifecycle ended.

    Four commands are excluded and named in
    :data:`COMMANDS_THAT_RUN_WITHOUT_ARGUMENTS`, because a bare invocation of
    them is a job rather than a question. Excluding them is not a weakening: a
    command that *runs* has not reported an unavailable capability, so there was
    never an exit ``10`` to find. What it removes is a recursive gate (D584).

    Measured before it was asserted: every command here returns in under half a
    second, and returns 2 -- except the four excluded, which do work.
    """
    result = run(str(REPO_ROOT / relative))
    assert result.returncode != 10, (
        f"{relative} returned 10 with no arguments, which the exit-code convention "
        "reserves for a capability that does not exist this session. FUTURE_STUBS is "
        "empty, so nothing should be reporting one."
    )


def test_the_excluded_commands_are_still_commands_and_still_refuse_a_bad_flag() -> None:
    """Guard the exclusion: it must not become a way to stop testing a command.

    Each excluded command is still in ``SHELL_COMMANDS`` -- so
    ``test_help_exits_zero_and_says_something`` and every other sweep still drive
    it -- and each still refuses an unknown flag with ``2``. That is the
    exit-code convention holding for them by a route that does not run the job.
    """
    for relative in COMMANDS_THAT_RUN_WITHOUT_ARGUMENTS:
        assert relative in SHELL_COMMANDS, f"{relative} was excluded out of the suite"
        result = run(str(REPO_ROOT / relative), "--definitely-not-a-flag")
        assert result.returncode != 10, (
            f"{relative} returned 10 for an unknown flag, which the convention "
            "reserves for an unavailable capability"
        )
        assert result.returncode != 0, (
            f"{relative} accepted --definitely-not-a-flag and exited 0, so it is not "
            "parsing its arguments at all"
        )


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
    """Every command, and every mode of one that has more than one.

    **`bin/doctor.sh --verbose` is here because this test was written when that
    command had one mode** (Session 11, ADR 0159). A flag added later is a flag
    the guard was not covering, and "verbose" is precisely the flag whose whole
    job is to print more — Question 5's shape, caught by asking it rather than by
    a leak.
    """
    planted = "APG_CANARY_VALUE_bH3x9Qf2"
    invocations = (
        ("bin/doctor.sh",),
        ("bin/doctor.sh", "--verbose"),
        # Session 17's rendering. Unprivileged it stops at the root check, so
        # this covers the shell half of the flag; the Python half is scanned
        # in test_doctor_redaction over every rendering.
        ("bin/doctor.sh", "--project", "apg-canary-dev", "--json"),
        ("bin/fleet.sh",),
        ("bin/fleet.sh", "--json"),
        (
            "bin/project-retire.sh",
            "--host",
            "host.example.yaml",
            "--project",
            "apg-canary-dev",
            "--confirm",
            "apg-canary-dev",
            "--record",
            "/dev/null",
            "--plan",
        ),
        ("bin/bootstrap-providers.sh",),
        ("bin/connect.sh",),
    )
    for relative, *arguments in invocations:
        result = run(str(REPO_ROOT / relative), *arguments, env={"APG_CANARY": planted})
        assert planted not in result.stdout + result.stderr, (
            f"{relative} {' '.join(arguments)} leaked its environment"
        )


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


def test_no_printf_format_string_begins_with_a_dash() -> None:
    """`printf '--mode ...'` is a usage error, not a line of output (D1199).

    bash's `printf` parses its first argument for options, so a format string
    beginning with `-` is read as one and the call fails:

        printf: usage error
        printf: usage: printf [-v var] format [arguments]

    Under `set -euo pipefail` that aborts the script. **Session 22's gate
    shipped three of them** -- the closing lines of all three modes, each
    wrapping onto a second `printf` that happened to begin with `--mode`. One
    was caught by running `--help`; the other two are printed only at the END
    of a successful run, so they were invisible until the gate was run to
    completion for the first time. The offline one aborted the gate AFTER it
    had written the evidence half, so the half was correct and the gate never
    said `PASSED`.

    This is the project's most-repeated class in its cheapest form: a line
    nobody had executed. Guarded here rather than in that gate's own module
    because the mistake is available to every command in `bin/`, and guarding
    the class rather than the instance is what D600 and D918 ask for.

    The remedy is `printf -- 'FORMAT'`, which is what the three now do.

    Goes red if: any shell command grows a `printf` whose format starts with a
    dash and is not preceded by `--`.
    """
    offenders: list[str] = []
    pattern = re.compile(r"""printf\s+(?!--\s)(['"])(-.*)""")

    for relative in SHELL_COMMANDS:
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            match = pattern.search(stripped)
            if match:
                offenders.append(f"{relative}:{number} {stripped[:80]}")

    assert not offenders, (
        "these printf format strings begin with a dash, so bash reads them as "
        f"options and the call fails: {offenders}. Use `printf -- 'FORMAT'`"
    )
