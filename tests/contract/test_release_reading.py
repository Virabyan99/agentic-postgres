"""The reading taken before a tag is cut (ADR 0214).

Behavioural, on `agentic_postgres.release_reading` and on `bin/release-reading.py`
with `git` faked. The split is the module's own: every conclusion is pure, so
each of the four outcomes is reachable from a constructed `Observation` rather
than from a repository shaped to produce it — which matters here more than
usual, because three of the four shapes only occur at a tag.

**What this file guards is an absence as much as a presence.** The command makes
no judgement about whether a tag is owed, and rig 28c is why: release bytes land
within one to five commits of every one of this repository's five tags, always,
because the next session starts, so the defect that cost `1.0.1` and `1.6.2` and
the ordinary between-releases state are the same shape. A verdict would be
invented. `test_the_reading_prints_no_instruction_about_the_tag` is the proof
that stays honest — adding one means deleting it.

`test_a_clone_without_tags_is_refused_rather_than_reported_clean` is the one that
ties this module to CI: two of the three jobs in `.github/workflows/ci.yml`
check out without tags, so a reading taken there would be clean by measuring
nothing (D600, ADR 0195).
"""

from __future__ import annotations

import importlib.util
import subprocess
from types import ModuleType
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, release_reading

pytestmark = [pytest.mark.contract, pytest.mark.p0]


def observation(**overrides: Any) -> release_reading.Observation:
    """A realistic observation of a tagged tree, overridable field by field."""
    base: dict[str, Any] = {
        "head": "a" * 40,
        "version": "1.6.2",
        "tags": ("1.0.0", "1.6.1", "1.6.2"),
        "tags_on_head": (),
        "last_tag": "1.6.2",
        "last_tag_commit": "b" * 40,
        "last_tag_date": "2026-09-16T18:38:08+04:00",
        "last_tag_version": "1.6.2",
        "version_tag": "1.6.2",
        "window_tag": "1.6.2",
        "commits_since_tag": 10,
        "paths_since_tag": ("src/agentic_postgres/diagnosis.py", "bin/doctor.py"),
        "bump_commit": "c" * 40,
        "bump_subject": "1.6.2: the patch that carries what 1.6.1's tag missed",
        "bump_paths": ("VERSION", "README.md"),
        "commits_since_bump": 11,
        "paths_since_bump": ("src/agentic_postgres/diagnosis.py",),
        "released_migrations_at_tag": 32,
        "released_migrations_in_tree": 33,
        "adrs_at_tag": 209,
        "adrs_in_tree": 214,
    }
    base.update(overrides)
    return release_reading.Observation(**base)


def command() -> ModuleType:
    """`bin/release-reading.py`, loaded as a module so `git` can be replaced.

    The product's own measuring half, not a re-implementation of it (D1114).
    """
    spec = importlib.util.spec_from_file_location(
        "apg_release_reading", REPO_ROOT / "bin" / "release-reading.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The four outcomes, and the order they are asked in
# ---------------------------------------------------------------------------


def test_a_clone_without_tags_is_refused_rather_than_reported_clean() -> None:
    """ADR 0195's third outcome, and it is not hypothetical.

    `actions/checkout` fetches no tags unless asked and two of this
    repository's three CI jobs use the default, so this is the shape a proof
    about tags would actually meet. Every other field here says *tagged, clean*
    — if the absence of tags were not asked first, this observation would be
    reported as `nothing_to_decide`, which is a clean answer nobody measured.
    """
    reading = release_reading.read(observation(tags=(), version_tag="1.6.2", commits_since_tag=0))
    assert reading.outcome == release_reading.NO_TAGS_IN_THIS_CLONE
    assert reading.questions == ()
    assert "cannot be taken" in reading.summary


def test_a_version_no_tag_carries_says_a_tag_is_owed() -> None:
    reading = release_reading.read(observation(version="1.7.0", version_tag="", window_tag="1.6.2"))
    assert reading.outcome == release_reading.TAG_IS_OWED
    assert "1.7.0" in reading.summary


def test_a_tagged_version_with_commits_since_names_what_the_tag_does_not_contain() -> None:
    """The shape that cost `1.0.1` and `1.6.2` — and the ordinary state too.

    It is 45 of this repository's first 147 commits, which is exactly why the
    summary reports and does not warn.
    """
    reading = release_reading.read(observation())
    assert reading.outcome == release_reading.TAG_DOES_NOT_CONTAIN_THESE
    assert "1.6.2" in reading.summary
    assert "10 commit(s)" in reading.summary


def test_a_tagged_version_with_nothing_since_has_nothing_to_decide() -> None:
    reading = release_reading.read(observation(commits_since_tag=0, paths_since_tag=()))
    assert reading.outcome == release_reading.NOTHING_TO_DECIDE


def test_the_four_outcomes_are_distinct_and_every_declared_one_is_reachable() -> None:
    """A guard against the class rather than the case (§7 question 5).

    An outcome constant nothing can produce is a branch that was renamed and
    left behind, and it reads exactly like a decision somebody made.
    """
    reached = {
        release_reading.read(observation(tags=())).outcome,
        release_reading.read(observation(version_tag="")).outcome,
        release_reading.read(observation()).outcome,
        release_reading.read(observation(commits_since_tag=0)).outcome,
    }
    assert reached == set(release_reading.OUTCOMES)


def test_the_window_named_in_the_sentence_is_the_one_the_count_was_measured_from() -> None:
    """Two tags in one paragraph is how a reader is taught to skim it.

    The names here are deliberately not version-shaped: two tags that are each
    other's substrings would let this pass on the wrong one.
    """
    reading = release_reading.read(
        observation(version_tag="carrying-tag", window_tag="carrying-tag", last_tag="describe-tag")
    )
    assert "tag carrying-tag carries it" in reading.summary
    assert "describe-tag" not in reading.summary


# ---------------------------------------------------------------------------
# The checklist the command prints, and the judgement it does not make
# ---------------------------------------------------------------------------


def test_the_three_questions_carry_the_release_and_are_asked_not_answered() -> None:
    reading = release_reading.read(observation())
    assert len(reading.questions) == 3
    assert all(question.endswith("?") for question in reading.questions)
    assert sum("1.6.2" in question for question in reading.questions) == 2
    rendered = "\n".join(release_reading.render(reading))
    for question in reading.questions:
        assert question in rendered


def test_a_reading_that_could_not_be_taken_asks_nothing() -> None:
    """Questions under a reading nobody took are a form of the same lie.

    Both halves, and the battery is why: the rendering returns early for this
    outcome, so a `Reading` carrying three questions nobody asked passed a
    version of this test that only read the printed lines.
    """
    reading = release_reading.read(observation(tags=()))
    assert reading.questions == ()
    rendered = "\n".join(release_reading.render(reading))
    assert "?" not in rendered.replace("(unknown)", "")
    assert "belong inside" not in rendered


def test_the_reading_prints_no_instruction_about_the_tag() -> None:
    """**The absence ADR 0214 is built on** (D1441's argument, one run later).

    Nothing separates *work that belonged inside the release* from *the next
    release's work* in the tree, so any verdict would be invented. Adding one
    means deleting this test, which is where the argument is kept.
    """
    forbidden = (
        "do not tag",
        "you should",
        "you must",
        "safe to tag",
        "ready to tag",
        "not ready",
        "warning",
        "error",
    )
    for case in (observation(), observation(version_tag=""), observation(commits_since_tag=0)):
        rendered = "\n".join(release_reading.render(release_reading.read(case))).lower()
        for phrase in forbidden:
            assert phrase not in rendered, f"{phrase!r} is a judgement this command does not make"


# ---------------------------------------------------------------------------
# What the rendering does with the facts
# ---------------------------------------------------------------------------


def test_a_count_that_could_not_be_read_prints_as_unknown_and_never_as_zero() -> None:
    """D600: a `null` that looks measured is worse than an absent field."""
    rendered = "\n".join(
        release_reading.render(
            release_reading.read(
                observation(
                    released_migrations_at_tag=None,
                    adrs_at_tag=None,
                )
            )
        )
    )
    assert "?" in rendered
    assert "0 -> 33" not in rendered
    assert "0 -> 214" not in rendered


def test_paths_are_grouped_by_the_directory_they_sit_in() -> None:
    """Grouping by the first two path COMPONENTS instead puts every `bin/`
    command on its own line, which is the wall the grouping exists to avoid.
    """
    grouped = dict(
        release_reading.group_paths(
            (
                "bin/doctor.py",
                "bin/doctor.sh",
                "bin/migrate.py",
                "tests/contract/test_a.py",
                "tests/contract/test_b.py",
            )
        )
    )
    assert grouped == {"bin": 3, "tests/contract": 2}


def test_a_file_at_the_repository_root_is_grouped_under_a_name() -> None:
    grouped = dict(release_reading.group_paths(("VERSION", "README.md", "bin/doctor.py")))
    assert grouped[release_reading.ROOT_GROUP] == 2
    assert "" not in grouped


def test_equal_groups_sort_by_name_so_two_runs_print_the_same_bytes() -> None:
    first = release_reading.group_paths(("zeta/one.py", "alpha/one.py"))
    second = release_reading.group_paths(("alpha/one.py", "zeta/one.py"))
    assert first == second == (("alpha", 1), ("zeta", 1))


def test_the_bump_window_is_not_printed_twice_when_it_is_the_same_window() -> None:
    """A tag on its own bump is the healthy arrangement; printing the identical
    list under it a second time teaches the reader to skip both.
    """
    same = ("src/agentic_postgres/diagnosis.py", "bin/doctor.py")
    rendered = "\n".join(
        release_reading.render(
            release_reading.read(observation(paths_since_tag=same, paths_since_bump=same))
        )
    )
    assert "the same files as above" in rendered
    assert rendered.count("  src/agentic_postgres") <= 1


# ---------------------------------------------------------------------------
# The measuring half, with `git` faked
# ---------------------------------------------------------------------------


def fake_git(answers: dict[tuple[str, ...], str | None]) -> Any:
    """A `git` that answers from a table and `None` for anything unasked.

    `None` for the unasked case deliberately: it is the module's own *could not
    be answered*, so a question this fake did not anticipate cannot be mistaken
    for an empty answer.
    """

    def run(*arguments: str) -> str | None:
        return answers.get(tuple(arguments))

    return run


def test_the_command_finds_the_tag_that_carries_the_version_not_the_one_on_head() -> None:
    """`1.6.1`'s tag sits one commit past its own bump.

    Asking whether HEAD is tagged would have called that release untagged for
    one commit and tagged for the next, which is a reading that changes its
    answer without anything changing.
    """
    module = command()
    #: `observe()` reads the checkout's own VERSION, so the fixture is built
    #: around it rather than around a constant that the next bump falsifies.
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    module.git = fake_git(
        {
            ("rev-parse", "HEAD"): "f" * 40,
            ("tag",): "older-tag\nthe-tag-carrying-it",
            ("show", "older-tag:VERSION"): "0.0.1",
            ("show", "the-tag-carrying-it:VERSION"): version,
            ("tag", "--points-at", "HEAD"): "",
            ("describe", "--tags", "--abbrev=0"): "older-tag",
            ("rev-list", "--count", "the-tag-carrying-it..HEAD"): "3",
        }
    )
    observed = module.observe()
    assert observed.tags == ("older-tag", "the-tag-carrying-it")
    assert observed.tags_on_head == ()
    assert observed.version_tag == "the-tag-carrying-it"
    #: And the window follows the version's tag, not `describe`'s answer, so the
    #: sentence and the count beneath it never name two different tags.
    assert observed.window_tag == "the-tag-carrying-it"
    assert observed.commits_since_tag == 3
    assert observed.last_tag == "older-tag"


def test_a_git_that_cannot_answer_leaves_a_count_unknown_rather_than_zero() -> None:
    """The count that was never read must not look like a count of nothing."""
    module = command()
    assert module.released_migrations(None) is None
    assert module.released_migrations("not json") is None
    assert module.released_migrations('{"migrations": null}') is None
    assert module.released_migrations('{"migrations": [1, 2, 3]}') == 3


def test_a_checkout_git_cannot_read_at_all_is_not_a_reading() -> None:
    module = command()
    module.git = fake_git({})
    assert module.observe() is None


def test_a_clone_with_no_tags_produces_the_third_outcome_through_the_command() -> None:
    module = command()
    module.git = fake_git({("rev-parse", "HEAD"): "e" * 40, ("tag",): ""})
    observed = module.observe()
    assert observed is not None
    assert observed.tags == ()
    assert release_reading.read(observed).outcome == release_reading.NO_TAGS_IN_THIS_CLONE


# ---------------------------------------------------------------------------
# The command as an operator meets it
# ---------------------------------------------------------------------------


def run_command(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(REPO_ROOT / "bin" / "release-reading.sh"), *arguments],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_the_command_takes_no_arguments_and_says_so() -> None:
    result = run_command("--since", "1.6.0")
    assert result.returncode == 2
    assert "takes no arguments" in result.stderr


@pytest.mark.parametrize("arguments", [("--help",), ("something", "--help")])
def test_help_is_answered_wherever_it_appears(arguments: tuple[str, ...]) -> None:
    """D1395/D1402/D1405: the class got bigger three times in Session 27."""
    result = run_command(*arguments)
    assert result.returncode == 0
    assert "release-reading" in result.stdout


def test_the_exit_code_follows_whether_this_clone_holds_tags() -> None:
    """End to end, and tied to a second measurement rather than to a constant.

    The gate's own CI job checks out with tags and the suite's does not, so
    asserting either exit code outright would be asserting which job is
    running. What is invariant is the RELATIONSHIP: no tags means the reading
    was refused, tags mean it was taken.
    """
    tags = subprocess.run(
        ["git", "tag"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    result = run_command()
    if tags.returncode != 0 or not tags.stdout.strip():
        assert result.returncode == 3
        assert "cannot be taken" in result.stdout
        return
    assert result.returncode == 0
    assert "The reading before a tag (ADR 0214)" in result.stdout
    assert "Is this commit the one the tag goes on?" in result.stdout
