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

from agentic_postgres import CURRENT_SESSION, REPO_ROOT

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

        usage = subprocess.run(
            [str(path), "--help"], capture_output=True, text=True, check=False, timeout=60
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
    match = re.search(r"Session (\d+) of 12 complete", readme)
    assert match, "the README has no 'Session N of 12 complete' status line"
    stated = int(match.group(1))
    assert stated == CURRENT_SESSION, (
        f"the README says Session {stated} is complete and CURRENT_SESSION is "
        f"{CURRENT_SESSION}. One of them is describing a release that does not exist"
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


def test_the_readme_points_at_the_index(readme: str) -> None:
    """An index nothing links to is a page nobody opens."""
    assert "docs/README.md" in readme
