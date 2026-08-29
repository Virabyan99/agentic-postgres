"""`DX-001`'s offline half — the documented path resolves and needs no source edit.

**What this can and cannot prove, said once.** It proves the path a new team
member is told to follow names commands that exist, passes arguments this release
accepts, and asks nobody to edit a tracked file. It **cannot** prove anybody
followed it, and `DX-001` does not report `passed` on this half alone (the plan's
§7). An offline half standing in for the whole is exactly the failure the
requirement exists to detect, and it is what a self-assessment of documentation
always does.

The session-numbered operator guides are **exempt from the argument checks and
that is not a loophole**: `docs/session-09-operator-guide.md` describes the
release that shipped in Session 9, and rewriting its flags to today's numbers
would destroy the record. What is checked is the path a reader is pointed at
*now*: `README.md` and the topic guides that carry no session in their name.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from agentic_postgres import CURRENT_SESSION, REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

#: The documents a reader who has just cloned this is pointed at.
#:
#: Session-numbered operator guides are deliberately absent: each describes the
#: release of its own session and is a record, not an instruction for today.
CURRENT_PATH_DOCUMENTS = (
    "README.md",
    "docs/README.md",
    "docs/api-operations.md",
    "docs/pool-operations.md",
    "docs/database-connections.md",
    "docs/migrations.md",
    "docs/backup-operations.md",
    "docs/secret-handling.md",
)

#: `--session N` and `--through-session N`, wherever they appear in prose or a
#: fenced block. Both spellings, because `materialize-secrets.sh` takes the first
#: and `deploy.sh` the second, and a reader meets them one after the other.
SESSION_ARGUMENT = re.compile(r"--(?:through-)?session[= ](\d+)")

#: A command this repository ships, as a documented line invokes it.
SHIPPED_COMMAND = re.compile(r"(?:^|[\s`(])(\./deploy\.sh|bin/[a-z0-9-]+\.(?:sh|py))")


def _tracked() -> set[str]:
    """Every path git has, so "is this a source file" is git's answer not mine."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return set(result.stdout.split())


def _documents() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in CURRENT_PATH_DOCUMENTS:
        path = REPO_ROOT / name
        if path.is_file():
            out[name] = path.read_text(encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# The control runs first
# ---------------------------------------------------------------------------


def test_the_scan_finds_the_commands_it_is_looking_for() -> None:
    """**The control.** A regex that matched nothing would report every document
    clean forever, which is D374 in a file whose whole subject is documentation.

    Asserts the parse finds the one command the path cannot omit — `./deploy.sh`
    — and that it finds documents at all.
    """
    documents = _documents()
    assert len(documents) >= 4, (
        f"only found {sorted(documents)}. CURRENT_PATH_DOCUMENTS names files that "
        "are not there, so the assertions below are about almost nothing"
    )
    found = {m.group(1) for text in documents.values() for m in SHIPPED_COMMAND.finditer(text)}
    assert "./deploy.sh" in found, (
        f"the command scan did not find ./deploy.sh in the documented path. It found "
        f"{sorted(found)[:10]}. The regex is not reading these documents"
    )
    assert len(found) >= 8, (
        f"the scan found only {len(found)} distinct commands ({sorted(found)}), which is "
        "fewer than the path demonstrably uses"
    )


# ---------------------------------------------------------------------------
# DX-001's offline half
# ---------------------------------------------------------------------------


def test_every_command_the_documented_path_names_is_shipped_and_executable() -> None:
    """A documented command that does not exist stops a reader at the step that
    names it, and one that is not executable stops them one step later with a
    `PermissionError` that reads like their own mistake.

    Mode is read from **the git index**, not the working tree: writing through
    `\\\\wsl$\\` strips the executable bit, so a tree can be right on the machine
    that wrote it and wrong for everybody who clones it.
    """
    tracked = _tracked()
    missing: list[str] = []
    not_executable: list[str] = []

    for name, text in _documents().items():
        for match in SHIPPED_COMMAND.finditer(text):
            command = match.group(1).lstrip("./")
            if command not in tracked:
                missing.append(f"{name} names {command}, which git does not have")
                continue
            mode = subprocess.run(
                ["git", "ls-files", "--stage", command],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split()
            if mode and mode[0] != "100755":
                not_executable.append(f"{command} is {mode[0]} in the index, not 100755")

    assert not missing, "the documented path names commands that do not exist:\n  " + "\n  ".join(
        sorted(set(missing))
    )
    assert not not_executable, (
        "the documented path names commands a reader could not run:\n  "
        + "\n  ".join(sorted(set(not_executable)))
    )


def test_the_documented_path_passes_session_numbers_this_release_accepts() -> None:
    """**D678, and this is the fourth time the class has appeared.**

    D505 and D507 were flags lost to retyping a previous session's guide. D678
    was three `--through-session 5` flags surviving from a Session 5 procedure
    into a Session 11 one, where 5 would have left `mcp`, `storage` and the
    backup plane on a superseded generation. Each was found by a person reading
    carefully, and each could have been found by this.

    A stale number here is worse than a missing command: the command runs, exits
    0, and deploys the wrong thing. `deploy.sh` refuses a number **above**
    `CURRENT_SESSION` (D59) and accepts anything below it, so the failure is
    silent by construction.

    Session-numbered operator guides are exempt and are not scanned — each
    describes its own release, and rewriting their flags would destroy the
    record they exist to be.
    """
    stale: list[str] = []
    for name, text in _documents().items():
        for line_number, line in enumerate(text.splitlines(), 1):
            for match in SESSION_ARGUMENT.finditer(line):
                value = int(match.group(1))
                if value != CURRENT_SESSION:
                    stale.append(f"{name}:{line_number} passes {match.group(0)!r}")

    assert not stale, (
        f"the documented path passes session numbers this release has left behind "
        f"(CURRENT_SESSION is {CURRENT_SESSION}). A reader following these deploys an "
        f"earlier session and the command exits 0:\n  " + "\n  ".join(stale)
    )


def test_no_documented_step_asks_a_reader_to_edit_a_tracked_file() -> None:
    """`DX-001`'s own words: *without source edits*.

    The path may ask a reader to **copy** an example and edit the copy —
    `project.example.yaml` to `project.yaml` — because the copy is gitignored and
    is the manifest the product is built around. What it may not do is tell them
    to change a file the repository ships, which is the difference between
    configuring a template and forking it.

    **`requirements-dev.in` is exempt, by name and with a reason.** The first
    version of this flagged *"To change a dependency, edit `requirements-dev.in`"*
    in the README, which is an instruction to somebody **developing the
    template**, not to somebody deploying a project. `DX-001` is about the
    deploy path. A category-shaped exemption would be a loophole; one named file
    with its reason attached is a decision somebody can disagree with.
    """
    contributor_inputs = {"requirements-dev.in"}
    tracked = _tracked()
    # The files a reader legitimately creates and edits. Each is gitignored, and
    # that is asserted rather than trusted: a manifest that became tracked would
    # make this test permissive at exactly the wrong moment.
    operator_inputs = ("project.yaml", "capabilities.yaml", "host.yaml")
    for name in operator_inputs:
        assert name not in tracked, (
            f"{name} is tracked, so 'edit {name}' is now a source edit and this test "
            "would no longer catch one"
        )

    instruction = re.compile(
        r"\b(?:edit|modify|change|update)\b[^.\n]{0,60}?`([^`]+)`", re.IGNORECASE
    )
    offenders: list[str] = []
    for name, text in _documents().items():
        for line_number, line in enumerate(text.splitlines(), 1):
            for match in instruction.finditer(line):
                target = match.group(1).strip().lstrip("./")
                if target in tracked and target not in contributor_inputs:
                    offenders.append(f"{name}:{line_number} says to edit {target}")

    assert not offenders, (
        "the documented path asks a reader to edit files this repository ships, which "
        "makes the template a fork:\n  " + "\n  ".join(offenders)
    )


def test_the_deploy_sequence_stays_within_the_specifications_bound() -> None:
    """The specification fixes it: *"fewer than 15 operator steps"* (§1.4).

    **Counted over the README's deploy sequence, not over every document.** The
    first version of this scanned all eight and reported 26 — which is true and
    measures nothing: `bin/rotate-signing-key.sh` and `bin/restore-test.sh` are
    documented operations, not steps on the path from a clone to a running
    deployment. A bound applied to the wrong set is a bound about nothing, and
    it would have been "fixed" by raising the number.

    The set is the fenced commands under `## Deploying`, which is the closest
    thing in this repository to the specification's numbered path. The
    specification counts steps a person takes and some of its steps are "read
    the summary"; this counts commands, which is the half that can grow without
    anybody noticing.

    Goes red if: the sequence from clone to running deployment grows past the
    bound the specification fixed.
    """
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Deploying", 1)
    assert len(section) == 2, "README.md has no '## Deploying' section to count"
    body = section[1].split("\n## ", 1)[0]

    commands = [match.group(1) for match in SHIPPED_COMMAND.finditer(body)]
    # The control: a section that parsed to nothing would satisfy any bound.
    assert commands, (
        "no commands were found under '## Deploying', so this bound is being "
        "applied to an empty set and would pass whatever the section said"
    )
    assert len(commands) < 15, (
        f"the deploy sequence is {len(commands)} commands and the specification fixes "
        f"the operator path at fewer than 15 steps: {commands}"
    )
