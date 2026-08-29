"""What a ``template_version`` bump permits (ADR 0162, `REL-COMPAT-001`).

The module is pure, so every one of these runs in a checkout and every mutant is
killable. What is deliberately NOT here is a test that the rules are *right* --
that is what the ADR decides. These assert that the code implements the ADR, and
one of them asserts the measurement the ADR rests on is still true.
"""

from __future__ import annotations

import pytest

from agentic_postgres import compatibility as compat

pytestmark = [pytest.mark.contract, pytest.mark.p0]


# ---------------------------------------------------------------------------
# Parsing: the grammar is semver.org's
# ---------------------------------------------------------------------------

ACCEPTED = [
    "0.1.0-dev",
    "0.2.0",
    "1.0.0",
    "1.0.0-rc.1",
    "0.1.0+build.5",
    "1.0.0-alpha.1+build.7",
    "10.20.30",
]

#: Every one of these is accepted by `packaging.version`. Listed as the things
#: this parser refuses rather than as "invalid strings", because the point is
#: not that they are nonsense -- it is that another parser in this very
#: virtualenv takes them.
REFUSED_BUT_PEP440_ACCEPTS = ["1.2", "01.2.3", "1.0.0.rc1"]

REFUSED = [*REFUSED_BUT_PEP440_ACCEPTS, "banana", "", "1.0.0-", "1.0.0+", "v1.0.0", "1.0.0.0"]


@pytest.mark.parametrize("value", ACCEPTED)
def test_an_accepted_version_round_trips(value: str) -> None:
    """``str(parse(v)) == v``.

    This is the property `packaging` does not have for the values this
    repository publishes: it returns `0.1.0.dev0` for `0.1.0-dev`. A parser whose
    output is not the document's string cannot be used to compare against one.
    """
    assert str(compat.parse(value)) == value


@pytest.mark.parametrize("value", REFUSED)
def test_a_refused_version_raises_rather_than_normalising(value: str) -> None:
    with pytest.raises(compat.CompatibilityError):
        compat.parse(value)


def test_a_trailing_newline_is_refused() -> None:
    """`\\Z`, not `$`.

    In Python `$` also matches immediately before a trailing newline, so
    `^...$` would accept a value read from a file with a stray newline -- and it
    would then fail to round-trip, silently. `installed_release.COMMIT_PATTERN`
    carries the same note for the same reason.
    """
    with pytest.raises(compat.CompatibilityError):
        compat.parse("1.0.0\n")


def test_parse_refuses_a_non_string() -> None:
    with pytest.raises(compat.CompatibilityError):
        compat.parse(100)  # type: ignore[arg-type]


def test_build_metadata_is_carried_and_ignored_by_precedence() -> None:
    """Semver's own rule: build metadata does not participate in precedence."""
    assert compat.parse("1.0.0+a").build == "a"
    assert compat.bump_between("1.0.0+a", "1.0.0+b") is None


def test_the_measurement_the_adr_rests_on_is_still_true() -> None:
    """ADR 0162's table, asserted rather than quoted.

    If a future `packaging` stops rewriting these, the ADR's reasoning has moved
    and somebody should know. If somebody swaps this parser for `packaging`, the
    round-trip test above goes red and this says why.
    """
    version_module = pytest.importorskip(
        "packaging.version", reason="packaging is undeclared; it is in the lock only transitively"
    )

    # It rewrites what this repository publishes.
    assert str(version_module.Version("0.1.0-dev")) == "0.1.0.dev0"
    assert str(version_module.Version("1.0.0-rc.1")) == "1.0.0rc1"

    # It accepts what semver refuses.
    for value in REFUSED_BUT_PEP440_ACCEPTS:
        version_module.Version(value)  # does not raise
        with pytest.raises(compat.CompatibilityError):
            compat.parse(value)

    # And it silently normalises one of them.
    assert str(version_module.Version("01.2.3")) == "1.2.3"


# ---------------------------------------------------------------------------
# The bump between two versions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("installed", "candidate", "expected"),
    [
        ("1.0.0", "2.0.0", compat.MAJOR),
        ("1.0.0", "1.1.0", compat.MINOR),
        ("1.0.0", "1.0.1", compat.PATCH),
        ("0.1.0-dev", "0.2.0", compat.MINOR),  # Run 7's actual bump
        ("0.2.0", "1.0.0", compat.MAJOR),  # Session 18's
        ("0.1.0-dev", "0.1.0", compat.PATCH),  # leaving prerelease
        ("0.2.0", "0.10.0", compat.MINOR),  # numeric, not lexical
        ("1.0.0", "1.0.0", None),  # equal
        ("2.0.0", "1.0.0", None),  # backwards
        ("0.1.0", "0.1.0-dev", None),  # into prerelease is backwards
        ("1.1.0", "1.0.9", None),
    ],
)
def test_bump_between(installed: str, candidate: str, expected: str | None) -> None:
    assert compat.bump_between(installed, candidate) == expected


def test_a_minor_bump_that_also_moves_patch_is_still_minor() -> None:
    """The level names the largest component that moved, not every one."""
    assert compat.bump_between("1.0.0", "1.1.3") == compat.MINOR
    assert compat.bump_between("1.0.5", "2.0.0") == compat.MAJOR


# ---------------------------------------------------------------------------
# What a set of changes requires
# ---------------------------------------------------------------------------


def test_no_changes_still_requires_a_bump() -> None:
    """A release that publishes nothing new is still a release.

    The deployed document records which one is installed, so a release that
    moved no version is one an upgrade plan cannot describe.
    """
    assert compat.required_level([]) == compat.PATCH
    assert compat.sufficient(proposed=None, required=compat.PATCH) is False


def test_the_largest_change_decides() -> None:
    assert (
        compat.required_level(["implementation", "migration_added", "image_digest"]) == compat.MINOR
    )
    assert compat.required_level(["migration_added", "secret_required_added"]) == compat.MAJOR


def test_an_unclassified_change_raises_rather_than_defaulting_to_patch() -> None:
    """An unclassified change is one nobody has decided about.

    Defaulting it to `patch` would make this answer a question it was never
    asked, which is the shape of every wrong permissive default in this
    repository's history.
    """
    with pytest.raises(compat.CompatibilityError) as caught:
        compat.required_level(["migration_added", "somebody_invented_this"])
    assert "somebody_invented_this" in str(caught.value)
    assert "migration_added" not in str(caught.value), (
        "the error names the classes it knows as well as the one it does not"
    )


@pytest.mark.parametrize(
    ("proposed", "required", "expected"),
    [
        (compat.MAJOR, compat.MINOR, True),
        (compat.MINOR, compat.MINOR, True),
        (compat.PATCH, compat.MINOR, False),
        (compat.PATCH, compat.PATCH, True),
        (compat.MAJOR, compat.PATCH, True),
        (None, compat.PATCH, False),
        (None, compat.MAJOR, False),
    ],
)
def test_sufficient(proposed: str | None, required: str, expected: bool) -> None:
    assert compat.sufficient(proposed=proposed, required=required) is expected


def test_sufficient_refuses_a_level_it_does_not_know() -> None:
    with pytest.raises(compat.CompatibilityError):
        compat.sufficient(proposed=compat.MINOR, required="enormous")
    with pytest.raises(compat.CompatibilityError):
        compat.sufficient(proposed="enormous", required=compat.MINOR)


# ---------------------------------------------------------------------------
# The tables themselves
# ---------------------------------------------------------------------------


def test_every_change_class_names_a_level_this_module_knows() -> None:
    """A table entry naming a level `sufficient` would raise on is a rule that
    cannot be applied, and it would only be discovered by a release needing it."""
    unknown = {
        name: level for name, level in compat.CHANGE_CLASSES.items() if level not in compat.LEVELS
    }
    assert not unknown, unknown


def test_the_input_digests_are_partitioned_against_the_ones_that_actually_exist() -> None:
    """ADR 0162's split: two are the operator's, three are the release's.

    Checked against what ``rendering.input_digests`` actually **returns**, by
    calling it, rather than against this module's own idea of the set. A
    partition compared only with itself is a description of itself (D277), and
    `input_digests`' whole contract is that it *"names every file the render
    depends on"* -- so a sixth digest arriving is precisely the event this must
    notice.
    """
    from agentic_postgres import REPO_ROOT, rendering

    produced = set(
        rendering.input_digests(
            REPO_ROOT / "project.example.yaml",
            REPO_ROOT / "capabilities.example.yaml",
        )
    )

    operator = set(compat.OPERATOR_DIGESTS)
    release = set(compat.RELEASE_DIGESTS)

    assert not (operator & release), f"a digest is claimed by both sides: {operator & release}"
    assert operator | release == produced, (
        "the partition and the render's actual digests disagree:\n"
        f"  classified but not produced: {sorted((operator | release) - produced)}\n"
        f"  produced but unclassified:   {sorted(produced - (operator | release))}"
    )
