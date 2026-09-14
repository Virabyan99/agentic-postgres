"""The README and the documentation index describe this repository (`DEP-001`).

**D623 is why this file exists.** `README.md` said *"Status: Session 3 of 12
complete"* for eight sessions. It named `bin/connect.sh` as unavailable, object
storage as a future session and backups as a future session — all three deployed
and proved. Nothing failed, because nothing checked.

The exit criterion of Session 11 is that a developer can follow the README from a
clean environment without undocumented commands. That is proved live on a host
(Run 8's rehearsal, Run 9's trip). What is provable **offline**, on every gate, is
narrower and is the half that goes stale silently:

* every command the README names exists and is executable;
* every page in `docs/` is indexed exactly once, and the index names no page that
  is not there;
* the README's stated session agrees with `CURRENT_SESSION`.

The third is the one that would have caught D623 in Session 4.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from agentic_postgres import CURRENT_SESSION, REPO_ROOT, template_version

pytestmark = [pytest.mark.contract, pytest.mark.p0]

README = REPO_ROOT / "README.md"
INDEX = REPO_ROOT / "docs" / "README.md"

#: Pages the index deliberately does not list as pages of its own.
#: `decisions/README.md` and the plans are indexed *as collections*, which is a
#: link the index does carry -- listing 161 ADRs and 11 plans individually would
#: make the index a directory listing rather than a map.
INDEX_EXEMPT: frozenset[str] = frozenset({"README.md"})


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def index() -> str:
    return INDEX.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Every command the README names is real
# ---------------------------------------------------------------------------


def readme_commands(text: str) -> set[str]:
    """`bin/*.sh` and `deploy.sh` mentioned anywhere in the README.

    Scanned out of the whole document rather than only the fenced blocks: a
    command named in prose is one a reader will try, and `deploy.sh` appears
    both ways.
    """
    found = set(re.findall(r"\bbin/[a-z0-9-]+\.(?:sh|py)\b", text))
    if "deploy.sh" in text:
        found.add("deploy.sh")
    return found


def test_the_readme_names_at_least_the_commands_a_reader_needs(readme: str) -> None:
    """The premise. A README that named no commands would satisfy every
    assertion below by describing nothing (D374)."""
    named = readme_commands(readme)
    assert len(named) >= 8, f"the README names only {sorted(named)}; it cannot be a usable path"
    for essential in ("deploy.sh", "bin/doctor.sh", "bin/connect.sh"):
        assert essential in named, f"the README does not mention {essential}"


def test_every_command_the_readme_names_exists(readme: str) -> None:
    """**D623's repair.** The README named `bin/connect.sh` as *"Session 4"* and
    unavailable while it was 697 lines of working code, and named a restore
    rehearsal as future while it had been run against a real deployment."""
    missing = sorted(c for c in readme_commands(readme) if not (REPO_ROOT / c).is_file())
    assert not missing, f"the README names commands that do not exist: {missing}"


def test_every_command_the_readme_names_is_executable(readme: str) -> None:
    """A reader copies the line as written. A command that is not executable
    fails with `Permission denied`, which reads as a broken repository rather
    than as a mode nobody set."""
    not_executable = sorted(
        c
        for c in readme_commands(readme)
        if (REPO_ROOT / c).is_file() and not (REPO_ROOT / c).stat().st_mode & 0o111
    )
    assert not not_executable, f"the README names non-executable commands: {not_executable}"


def test_the_readme_names_no_command_that_is_a_future_stub() -> None:
    """`FUTURE_STUBS` is empty today, and this is what keeps that true of the
    README specifically: a command that exits 10 *"unavailable this session"* is
    one a reader would be told to run and then refused."""
    from tests.contract.test_cli_contract import FUTURE_STUBS

    named = readme_commands(README.read_text(encoding="utf-8"))
    offered = sorted(set(FUTURE_STUBS) & named)
    assert not offered, f"the README offers commands that are still stubs: {offered}"


def test_every_flag_the_readme_shows_appears_in_that_commands_usage() -> None:
    """**Run 7 wrote three README lines a reader could not run**, and only
    executing them found it: `migrate.sh --project` takes a manifest FILE and the
    draft passed a key, and `connect.sh tunnel` also needs `--ssh USER@HOST`.
    That is D505/D507/D602's family — a flag or a step lost to retyping — landing
    inside the run written to prevent it.

    What this catches is the **invented** flag: one the README shows and the
    command does not have. What it cannot catch is the **omitted** required flag,
    because an absence is not a token to scan for. That half is Run 8's
    rehearsal, and it is said here so nobody reads this test as covering both.

    **The dispatcher is asked its VERB's usage** (D1196). `bin/apg.sh` is a
    front door: `apg.sh dev up --project FILE` documents `--project` in
    `bin/dev.sh --help`, and the dispatcher's own help lists verbs rather than
    flags. Asking the front door about a flag it delegates reports every README
    line that goes through it as invented, which is what made this test red the
    first time the README showed one. Resolved rather than exempted -- the line
    is checked against the verb's usage, so a flag nobody documents anywhere is
    still caught.
    """
    text = README.read_text(encoding="utf-8")
    problems: list[str] = []

    for line in text.splitlines():
        stripped = line.strip().removeprefix("sudo ").strip()
        match = re.match(r"^((?:\./)?(?:bin/)?[a-z0-9-]+\.sh)\s+(.*)$", stripped)
        if not match:
            continue
        relative = match.group(1).removeprefix("./")
        path = REPO_ROOT / relative
        if not path.is_file():
            continue

        arguments = ["--help"]
        rest = match.group(2).split()
        if relative == "bin/apg.sh" and rest and re.fullmatch(r"[a-z][a-z-]+", rest[0]):
            arguments = [rest[0], "--help"]

        usage = subprocess.run(
            [str(path), *arguments], capture_output=True, text=True, check=False, timeout=60
        )
        documented = usage.stdout + usage.stderr
        # The comment half of a line is prose, not an invocation.
        invocation = match.group(2).split("#")[0]
        for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", invocation):
            if flag not in documented:
                problems.append(f"{relative} {flag}")

    assert not problems, (
        f"the README shows flags these commands do not document: {sorted(set(problems))}. "
        "A reader copies the line as written"
    )


# ---------------------------------------------------------------------------
# The stated session is the real one
# ---------------------------------------------------------------------------


def test_the_readme_states_the_session_the_release_implements(readme: str) -> None:
    """**The assertion that would have caught D623 in Session 4.**

    The README's status line is a claim about the release, and it went eight
    sessions without one thing checking it. `CURRENT_SESSION` is the number the
    gate and `deploy.sh` both read, so it is the number the README must agree
    with.
    """
    # "implemented" rather than "complete", and the change is a correction
    # rather than a loosening (D672). `CURRENT_SESSION` is *what this release
    # implements* -- the number `deploy.sh` refuses to exceed -- and it moves
    # when the code lands, which is before the host evidence is published.
    # "Complete" conflated the two, and the assertion below is unchanged: one
    # number, and it must equal `CURRENT_SESSION`.
    # **`of 12` was a typed total and Session 13 outlived it.** Stage 1 ran to
    # twelve and the phrase was true for all of it; Stage 2 runs 13-18, so a
    # status line reading "Session 13 of 12" is nonsense, and "of 18" would
    # encode the next stage's length into a guard with no business knowing it.
    # What this checks is the number that can disagree with the release. D719's
    # class again: a literal that was right until the world gained a case.
    match = re.search(r"Session (\d+) implemented", readme)
    assert match, "the README has no 'Session N implemented' status line"
    stated = int(match.group(1))
    assert stated == CURRENT_SESSION, (
        f"the README says Session {stated} is complete and CURRENT_SESSION is "
        f"{CURRENT_SESSION}. One of them is describing a release that does not exist"
    )


def test_the_readme_states_the_template_version_the_release_carries(readme: str) -> None:
    """**D936.** The README quoted `template_version` 0.2.0 through two bumps.

    The session line above has been checked since Session 12; the version
    beside it was checked by nobody, so it said 0.2.0 while `VERSION` said
    0.4.0 for two whole releases. Same file, same sentence, one number guarded
    and one not -- D719's class in the guard that exists for it.
    """
    match = re.search(r"`template_version` \*\*([0-9A-Za-z.+-]+)\*\*", readme)
    assert match, "the README has no `template_version` **N** status phrase"
    assert match.group(1) == template_version(), (
        f"the README says template_version {match.group(1)} and VERSION says "
        f"{template_version()}. One of them is describing a release that does not exist"
    )


def test_the_deploy_examples_target_a_session_this_release_can_deploy(readme: str) -> None:
    """`deploy.sh` refuses `--through-session N` above what the release
    implements, so a README example above it is a copied line that exits 10."""
    for session in re.findall(r"--through-session (\d+)", readme):
        assert int(session) <= CURRENT_SESSION, (
            f"the README shows --through-session {session}; this release deploys "
            f"through {CURRENT_SESSION} and would refuse it"
        )
    for session in re.findall(r"--session (\d+)", readme):
        assert int(session) <= CURRENT_SESSION, (
            f"the README shows --session {session}, above what this release implements"
        )


# ---------------------------------------------------------------------------
# The index is complete, in both directions
# ---------------------------------------------------------------------------


def documentation_pages() -> set[str]:
    return {path.name for path in (REPO_ROOT / "docs").glob("*.md")} - INDEX_EXEMPT


def indexed_pages(index: str) -> set[str]:
    return set(re.findall(r"\(([a-z0-9-]+\.md)\)", index))


def test_every_documentation_page_is_indexed(index: str) -> None:
    """Goes red when a page is added to `docs/` and not listed. That is the whole
    point, and the fix is one line in the index rather than a change here —
    `test_every_command_in_bin_is_covered_by_this_module` is the same guard for
    `bin/`, and it caught `bin/doctor.py` within a minute of the file existing."""
    unindexed = sorted(documentation_pages() - indexed_pages(index))
    assert not unindexed, (
        f"these pages are in docs/ and absent from docs/README.md: {unindexed}. An index "
        "that has quietly stopped being complete is worse than none: it tells a reader "
        "the set is whole"
    )


def test_the_index_names_no_page_that_is_not_there(index: str) -> None:
    """The other direction. A link to a deleted page is a reader's dead end, and
    a one-directional check would never see it."""
    phantom = sorted(indexed_pages(index) - documentation_pages())
    assert not phantom, f"docs/README.md links to pages that do not exist: {phantom}"


def test_no_page_is_indexed_twice(index: str) -> None:
    """Two rows for one page are two descriptions that will diverge."""
    links = re.findall(r"\(([a-z0-9-]+\.md)\)", index)
    duplicated = sorted({name for name in links if links.count(name) > 1})
    assert not duplicated, f"these pages appear more than once in the index: {duplicated}"


def test_the_index_marks_what_is_generated(index: str) -> None:
    """A reader who hand-edits a generated page loses the edit on the next render.
    The index says which pages those are, because that is where a reader looks
    before opening one."""
    assert "generated" in index.lower()
    assert "acceptance-matrix.md" in index


def test_the_render_reports_the_modes_it_actually_gave() -> None:
    """**D652.** Session 10 added `pgbackrest.conf` to the render's closing line
    and left the claim at *"(mode 0600)"*. That file is `0444` on purpose — it
    carries no credential by construction and uid 999 reads it — so the one
    sentence every render prints asserted a mode the renderer had never given.

    Question 5: true when written, false once a file with a different mode joined
    the list it describes. The repair is that the modes come from the constants,
    so the next file with a third mode moves this line instead of contradicting
    it.
    """
    from agentic_postgres import rendering

    source = (REPO_ROOT / "bin" / "render-config.py").read_text(encoding="utf-8")
    closing = source.split('print(summary, end="")')[1].split("No service was started")[0]

    assert "rendering.FILE_MODE" in closing and "rendering.PGBACKREST_CONF_MODE" in closing, (
        "the render's closing line types its modes instead of reading them"
    )
    assert rendering.FILE_MODE != rendering.PGBACKREST_CONF_MODE, (
        "the two modes are equal, so this test cannot tell a derived claim from a "
        "typed one and proves nothing (D374)"
    )


def test_the_readme_states_both_generated_modes(readme: str) -> None:
    """A reader who is told everything is `0600` and finds a `0444` file has been
    given a document they cannot trust about the next thing either."""
    from agentic_postgres import rendering

    assert f"{rendering.FILE_MODE:04o}" in readme
    assert f"{rendering.PGBACKREST_CONF_MODE:04o}" in readme, (
        "the README does not mention pgbackrest.conf's mode, which is not 0600"
    )


@pytest.mark.parametrize("arguments", [(), ("--verbose",)])
def test_doctor_reaches_its_own_conclusion(arguments: tuple[str, ...]) -> None:
    """**D654**, and the README's *"confirm the workstation is ready"* step.

    `bin/doctor.sh` with no arguments exited **1 after four lines** for an entire
    run. Run 4 added `[ -n "${VERBOSE}" ] && printf` as the last statement of
    `check_command`; under `set -e` a function whose last command returns 1
    returns 1, so the script died on the first tool it found while VERBOSE was
    empty. **`--verbose` was unaffected**, because there the test succeeds — and
    `--verbose` is the mode Run 4 exercised.

    Nothing caught it. `test_cli_contract` checks `--help`, which returns before
    any check runs; the planted-environment test reads the output and not the
    exit code. Question 1 — *what would have to break for this to go red?* —
    had no answer for this command's default path.

    So the assertion is not about a verdict. It is that the command **reaches
    its own conclusion**: 0 when satisfied, 3 when something is missing, and its
    summary line either way. Truncation is the symptom, and both modes are
    parametrised because a mode added later is a mode a guard was not covering.
    """
    result = subprocess.run(
        [str(REPO_ROOT / "bin" / "doctor.sh"), *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
        cwd=REPO_ROOT,
    )
    output = result.stdout + result.stderr

    assert result.returncode in (0, 3), (
        f"bin/doctor.sh {' '.join(arguments)} exited {result.returncode}. The documented "
        f"codes are 0 (ready) and 3 (a prerequisite is missing); anything else means it "
        f"died partway.\n{output}"
    )
    assert "prerequisite" in output, (
        f"bin/doctor.sh {' '.join(arguments)} printed no summary line, so it stopped before "
        f"reaching its own conclusion:\n{output}"
    )
    # The last section it prints. Its absence is what "died after four lines"
    # looked like, and an exit code alone would not have shown it.
    assert "Repository shape" in output, (
        f"bin/doctor.sh {' '.join(arguments)} never reached the repository-shape section"
    )


def test_the_readme_points_at_the_index(readme: str) -> None:
    """An index nothing links to is a page nobody opens."""
    assert "docs/README.md" in readme


# ---------------------------------------------------------------------------
# What an adopter has to be told before they start (D1040, D1056)
# ---------------------------------------------------------------------------


def test_the_readme_tells_an_adopter_what_adding_a_table_costs() -> None:
    """D1040. Every fact was already in the repository -- in
    docs/source-specification.md §5.4, in the contract file's own header, in
    `bin/api-contract.sh --help` -- and nowhere was it collected into the
    sequence an adopter actually performs.

    The one that changes the shape of the work is the snapshot: it is captured
    from a running deployment and refuses a hand edit, so a first bring-up
    necessarily runs with that check red and an adopter has to know that is
    expected rather than a mistake they made.

    **ADR 0198 changes what this section has to say, not whether it says it.**
    Written in Session 19, it asserted the README states there is *"no tenant
    extension point"* -- the honest answer at the time, and the fact ADR 0197
    answered `DX-001` "no" over. Session 20 built one, so that assertion is
    replaced rather than dropped: the section must now name the directory an
    adopter owns, and must say that none of the release's files is edited --
    which is the property the seven-file count in ADR 0197 measured the absence
    of.
    """
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    # The newlines are load bearing. Without them this is a PREFIX, and a
    # battery renaming the heading to "## Adding your own tables REMOVED"
    # left this assertion green -- D200's shape, which this repository has
    # already paid for once in test_api_migrations.py's HOOK_DEFINITION.
    assert "\n## Adding your own tables\n" in readme, (
        "the README does not tell an adopter what adding a table costs; every "
        "fact is elsewhere in the repository and none of it is in the order it "
        "is needed"
    )
    section = readme.split("\n## Adding your own tables\n", 1)[1].split("\n## ", 1)[0]

    # Where the adopter's own files go (ADR 0198). Named exactly, because the
    # whole repair is WHICH files a fork touches.
    assert "projects/<slug>" in section, (
        "the section does not name the directory an adopter owns; without it the "
        "instruction is 'fork and edit', which is what ADR 0197 measured at seven "
        "release files"
    )
    assert "schema_version: 5" in section, (
        "the section does not show the manifest key that declares a set, so an "
        "adopter has the directory and no way to point at it"
    )
    assert "you do not touch" in section.lower(), (
        "the section does not say which of the release's files an adopter leaves "
        "alone -- and that list IS the repair; without it a reader cannot tell "
        "this from the fork-and-edit instruction it replaces"
    )

    # The two that were discovered the expensive way and are unchanged in kind.
    assert "postgrest-openapi.canonical.json" in section, "the snapshot is not named"
    assert "before your first deploy" in section, (
        "the section does not say the snapshot check is red until after a deploy, "
        "which is the fact that turns a dead end into an instruction"
    )

    # What the release will refuse in a project's set, before it renders it.
    # An adopter who meets one of these on a host has already written the
    # migration; meeting it in the README costs nothing.
    assert "FORCE ROW LEVEL SECURITY" in section, (
        "the section does not say a table in `app` must carry FORCE row level "
        "security, which is the refusal an adopter is most likely to hit"
    )
    assert "app_private" in section, "the section does not say the platform's state is off limits"


def test_the_readme_says_what_closes_the_agent_plane_and_how_a_project_opens_it() -> None:
    """**Replaces `test_the_readme_says_the_agent_plane_does_not_serve_an_adopters_tables`**
    under ADR 0200, and it is stricter: the old guard held the README to a
    closure that no longer exists (D1056's two, both removed in Session 21),
    and this one holds it to what closes the plane NOW and to the way in.

    What must be said, because an adopter reads it before building: a scope is
    derived from a relation the reviewed surface publishes and the compiler
    refuses any other; the runtime registers what the compiler signed; a
    project opens the plane by owning a capability manifest (ADR 0201); and a
    borrowed scope is still caught. What must NOT be said any more is the old
    closure, because a README that kept it would send an adopter away from a
    door that is open.
    """
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## What is intentionally unavailable", 1)[1].split("\n## ", 1)[0]

    assert "ADR 0200" in section, "the opening of the agent plane is not attributed"
    assert "derived from a relation the reviewed surface publishes" in section, (
        "the README does not say where a scope comes from now"
    )
    assert "compiler refuses" in section, "the compiler's approval is not stated"
    assert "refuses a lock the compiler did not sign" in section, (
        "the README does not say what replaced the six-name roster"
    )
    assert "capability manifest" in section and "ADR 0201" in section, (
        "the README does not say how a project opens the plane to its own tables"
    )
    assert "borrows `notes:read`" in section, "the borrowed-scope catch is no longer stated"
    # The old closure must be gone, not merely contradicted somewhere else.
    for stale in ("closed enum", "exactly six names", "no agent surface at all"):
        assert stale not in section, f"the README still states the old closure: {stale!r}"


# ---------------------------------------------------------------------------
# The second walk's page (Session 25, ADR 0207)
# ---------------------------------------------------------------------------


SECOND_WALK = REPO_ROOT / "docs" / "second-walk.md"
TASK_BEGIN = "<!-- task-statement:begin -->"
TASK_END = "<!-- task-statement:end -->"


def test_the_second_walk_page_carries_the_task_statement_and_the_record_schema() -> None:
    """The statement is copied verbatim into a fresh session, so it is an
    ARTEFACT with a boundary rather than a passage somebody paraphrases.

    Two literal markers, because a builder handing the walk over reads
    "everything between these" and a human eye cannot be trusted to find the
    end of a prose section under time pressure. What is asserted here is that
    the markers exist exactly once each, in order, with a statement of real
    size between them; that the statement carries every rule the walk depends
    on; and that the page's schema section names every field the READER
    requires -- read out of `dx_record` rather than typed, so a field added to
    the reader and not to the page is caught here rather than by a walker who
    wrote a record the product refuses.
    """
    from agentic_postgres import dx_record

    text = SECOND_WALK.read_text(encoding="utf-8")
    assert text.count(TASK_BEGIN) == 1 and text.count(TASK_END) == 1, (
        "the task statement's markers are not each present exactly once, so 'everything "
        "between them' does not name one passage"
    )
    assert text.index(TASK_BEGIN) < text.index(TASK_END), "the markers are in the wrong order"
    statement = text[text.index(TASK_BEGIN) + len(TASK_BEGIN) : text.index(TASK_END)]
    assert len(statement.split()) >= 300, (
        f"the task statement is {len(statement.split())} words. It is the WHOLE prompt of a "
        "session that has nothing else, and a short one is a walk the builder filled in later"
    )

    # Each of these is a rule the walk's validity rests on, and a statement
    # missing one produces a record nobody can read as evidence (ADR 0207 §1).
    required = {
        "~/walk/agentic-postgres": "the clone's path",
        "~/walk/dx-record.json": "where the record goes",
        "docs/plans/": "the one directory a walker may not read",
        "wsl bash -lc": "the shell, when the walk is driven from Windows",
        "dx-record digest": "the first of the two closing commands",
        "dx-record check": "the second",
        "Ask nobody": "that a question is an undocumented step",
        "sudo": "that no host, credential or deploy is in scope",
        "reached_success_criterion": "the walker's own verdict",
        "blocked_by": "what a walk that stopped owes",
        "undocumented step": "what the walk is actually collecting",
    }
    for needle, why in required.items():
        assert needle in statement, f"the task statement does not name {why} ({needle!r})"

    # The schema section names what the reader requires. Derived, not typed:
    # a field added to `dx_record.REQUIRED_FIELDS` and not to this page would
    # otherwise reach a walker as a refusal of a record they wrote correctly.
    schema = text.split("## 3. The record", 1)
    assert len(schema) == 2, "the page has no record-schema section"
    body = schema[1].split("\n## ", 1)[0]
    for field in dx_record.REQUIRED_FIELDS:
        assert field in body, f"the record's schema section does not describe {field!r}"
    for field in dx_record.FOLLOWED_BY_FIELDS:
        assert field in body, f"the schema section does not describe followed_by.{field}"

    # **`blocked_by` is the one member that is not a row of the table**, so it
    # has to be described in the section's PROSE. A battery deleting its
    # paragraph left `assert "blocked_by" in body` green, because the row for
    # `reached_success_criterion` mentions it in passing -- D200's shape, a
    # substring standing in for a description. What is required now is a
    # paragraph that names the field AND the condition under which it is read;
    # a walker who is told only that the field exists does not know when to
    # write one.
    prose = [
        paragraph
        for paragraph in body.split("\n\n")
        if not paragraph.lstrip().startswith("|") and "blocked_by" in paragraph
    ]
    assert any("reached_success_criterion" in paragraph for paragraph in prose), (
        "the schema section does not say when `blocked_by` is required. It is the only "
        f"member outside the table, and the prose paragraphs naming it are {prose}"
    )

    # And the page is reachable: the index proof above only checks that every
    # page is listed once, which a page listed under the wrong heading passes.
    index = INDEX.read_text(encoding="utf-8")
    assert "(second-walk.md)" in index, "the second walk's page is not in the index"
