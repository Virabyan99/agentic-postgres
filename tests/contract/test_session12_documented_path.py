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
    # **D1323.** The guide IS the documented path -- it is what
    # `docs/README.md` sends a new reader to first -- and it was not in this
    # set for thirteen sessions, while `dx_record.DOCUMENT_ROOTS` (the LIVE
    # half's scan) does read it. The two halves of one claim were reading
    # different documents. Added here rather than removed there: the guide is
    # the page most likely to name a command that has moved.
    "docs/new-team-member.md",
    # The statement a walker is handed. If it names a command that does not
    # exist, the walk fails on the builder's typing rather than on the product.
    "docs/second-walk.md",
    # **D1383, and it is D1323's shape a second time.** The upgrade guide and
    # the current operator guide are what an operator holds; neither was in
    # this set nor in `dx_record.DOCUMENT_ROOTS`, so the two halves of one
    # claim were again reading different documents -- and eighteen defects in
    # those pages were found by a cold reader rather than by this suite. ADR
    # 0209 decides they are part of the release; this is where the release
    # checks them.
    "docs/operator-guide.md",
    "docs/upgrade-guide.md",
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


# ---------------------------------------------------------------------------
# `DX-DOC-001` -- the guide is the path this release has, and the README is in
# the order an adopter walks it (Session 25, D1313, D1329)
# ---------------------------------------------------------------------------


GUIDE = REPO_ROOT / "docs" / "new-team-member.md"

#: The label the guide is allowed to carry, and the only one.
#: The labels a step's heading may carry, and every one of them is MEASURED off
#: the page rather than imagined. Run 4 asserted the single label `*available
#: now*` against every step, which was true of the page it was written for; the
#: second walk then found that two steps cannot honestly claim it, because the
#: compile and the generate wait on a snapshot only a deployment produces
#: (D1357). Widening to the set the page uses is not a weakening -- CLAUDE.md's
#: line is that widening an allowlist to a MEASURED set is not, and loosening it
#: to a subset check is. The check below got stricter in the same move: it is
#: now per-step, so a step carrying NO label fails, where the old count would
#: have absorbed that as long as some other step carried two.
STEP_LABELS = (
    "*available now*",
    "*the manifest now, the compile after your first deploy*",
    "*after your first deploy, if you added a table*",
)

#: What the guide claimed for fifteen sessions about steps that were built,
#: deployed and measured. Both spellings, with and without a session number.
FUTURE_LABEL = re.compile(r"future session(?:\s*\((\d+)\))?", re.IGNORECASE)


def test_the_guide_labels_nothing_as_future_that_this_release_implements() -> None:
    """**D1313.** The guide's step 14 said *future session (10)* while the
    restore it describes had been rehearsed against a real deployment and
    timed at 247 s; step 12 said *implemented in Session 2* thirteen sessions
    later; and its *done* section told a reader they had no database in the
    paragraph after the one that had just given them one.

    D693's guard catches a stale `--session N` an operator would TYPE. It
    cannot catch a stale sentence, because a sentence is not an argument -- and
    the guide is the one document whose whole purpose is to be read by a
    stranger. This is that half.

    The rule is the strong one and it is what the page can now honestly claim:
    **no `future session` label at all.** A label carrying a number this
    release has passed is a lie about the product; a label carrying no number
    is a lie a reader cannot even check.

    The control is in the same test: the scan finds the label vocabulary the
    page does use, so a page that had been emptied would not pass by having no
    labels to fault.
    """
    text = GUIDE.read_text(encoding="utf-8")

    # The control first. A guide with no labels at all would satisfy the
    # assertion below about nothing (D374).
    steps = re.findall(r"^### (\d+)\. .+$", text, flags=re.MULTILINE)
    assert len(steps) >= 10, f"the guide has {len(steps)} numbered steps; it is not a path"
    assert [int(number) for number in steps] == list(range(1, len(steps) + 1)), (
        f"the guide's steps do not run 1..{len(steps)}: {steps}. A reader following a page "
        "whose numbers skip cannot tell a missing step from a renumbering"
    )
    headings = re.findall(r"^### \d+\. .+$", text, flags=re.MULTILINE)
    unlabelled = [
        heading for heading in headings if not any(label in heading for label in STEP_LABELS)
    ]
    assert not unlabelled, (
        f"these steps carry no label this scan knows: {unlabelled}. Either a step was "
        f"added without one, or the page's vocabulary moved and {list(STEP_LABELS)} did "
        "not move with it -- and a scan looking for words the page no longer uses "
        "reports nothing and passes"
    )
    assert any("*available now*" in heading for heading in headings), (
        "no step is labelled *available now*; the page cannot be all deferral"
    )

    stale: list[str] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for match in FUTURE_LABEL.finditer(line):
            session = match.group(1)
            if session is None or int(session) <= CURRENT_SESSION:
                stale.append(f"docs/new-team-member.md:{line_number}: {line.strip()!r}")

    assert not stale, (
        f"the guide labels steps as belonging to a future session, and this release "
        f"implements through {CURRENT_SESSION}. A reader is told the product cannot do "
        f"something it has been doing for a year:\n  " + "\n  ".join(stale)
    )


def test_the_guide_names_the_tenant_path_and_the_three_surfaces() -> None:
    """The guide is the walk's own page, so it has to contain the walk.

    Stage 3 gave an adopter four things the guide named none of: a directory of
    their own, a local database, a generated client and Studio. A walker
    following a page that stops at *render* would record every one of them as
    an undocumented step -- correctly, and about the documentation rather than
    about the product.

    The `done` section is checked for the tenant path specifically, because
    that is the sentence that was wrong in the most misleading way: it said
    *"You do not have a running database. That is Session 3"* one paragraph
    after the step that builds one.
    """
    text = GUIDE.read_text(encoding="utf-8")

    # **Either spelling of a surface counts**, because both are documented and
    # `dx_record.normalise` resolves them to one for exactly this reason: the
    # guide writes `bin/apg.sh dev up`, README writes both, and a guard that
    # demanded the bare `apg dev` would be holding the page to a spelling no
    # page uses. What is asserted is that the surface is REACHED, not how it
    # was typed.
    surfaces = {
        "the local database": ("apg dev ", "apg.sh dev ", "bin/dev.sh"),
        "the generated client": ("apg generate", "apg.sh generate", "bin/generate.sh"),
        "Studio": ("apg studio", "apg.sh studio", "bin/studio.sh"),
        "a directory of the reader's own": ("projects/<slug>",),
    }
    for surface, spellings in surfaces.items():
        assert any(spelling in text for spelling in spellings), (
            f"the guide never reaches {surface} (looked for {list(spellings)}); a reader "
            "following it reaches a `done` that does not describe what this release does"
        )

    marker = '\n## What "done" looks like'
    assert marker in text, "the guide has no `done` section, which is the walk's own criterion"
    done = text.split(marker, 1)[1].split("\n## ", 1)[0]
    for named in ("projects/<slug>", "dx-record check", "gate"):
        assert named in done, (
            f"the guide's `done` section does not name {named!r}, so it is not the success "
            "criterion a walk is measured against (ADR 0207 §4)"
        )
    # The sentence that was wrong, gone rather than contradicted elsewhere.
    for stale in ("That is Session 3", "You do not have a running database"):
        assert stale not in text, f"the guide still says {stale!r}"


#: The order an adopter walks the README, and the reason the sections moved.
#: Read as a list rather than asserted pairwise: what matters is the sequence,
#: and a pairwise check passes on an order that is right in every pair and
#: wrong overall.
ADOPTER_WALK = (
    "What runs",
    "Local bootstrap",
    "Rendering a project",
    "A local environment",
    "Adding your own tables",
    "Giving an agent your tables",
    "A generated client",
    "Studio",
    "Deploying",
    "Operating a deployment",
    "Checks",
)


def test_the_readme_sections_are_in_the_order_an_adopter_walks() -> None:
    """**D1329.** The README described the product in the order it was BUILT.

    Studio and the generated client -- Sessions 24 and 23 -- came before the
    two sections that tell a reader how to add a table at all, so a reader met
    a client over "your surface" nine hundred words before the section that
    lets them have one. Every section's prose is untouched by the reorder and
    that is asserted elsewhere: two proofs in this suite hold sentences inside
    two of them, and they are unchanged.

    The tail after *Checks* is deliberately not constrained. It is reference
    material -- Compose, version locks, the exit-code convention, the
    repository map -- and fixing its order here would be a guard with an
    opinion nobody has argued for.
    """
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## (.+)$", text, flags=re.MULTILINE)

    missing = [name for name in ADOPTER_WALK if name not in headings]
    assert not missing, f"the README has no sections named {missing}"

    walked = [name for name in headings if name in ADOPTER_WALK]
    assert walked == list(ADOPTER_WALK), (
        "the README's sections are not in the order an adopter walks them.\n"
        f"  expected: {list(ADOPTER_WALK)}\n"
        f"  found:    {walked}"
    )

    # The control: the walk is a PREFIX of the document, so nothing in the
    # reference tail has drifted up into the middle of the path.
    assert headings[: len(ADOPTER_WALK)] == list(ADOPTER_WALK), (
        f"a section that is not part of the adopter's path appears inside it: "
        f"{headings[: len(ADOPTER_WALK)]}"
    )
