"""The env-file disjointness check, and the locale that made it lie.

``bin/compose.sh`` proves that no two ``--env-file`` files define the same
variable, so no ordering between them can silently override anything. The proof
was ``sort`` piped into ``comm -12``.

``sort`` collates by locale. Under ``en_US.UTF-8`` it treats ``_`` as ignorable
at the primary level, and ``comm`` — which wants byte order — then reports "input
is not in sorted order". It reports it and *keeps going*, and the answer it
produces from that point can omit overlaps that are really there.

So on a UTF-8 host the check could return "disjoint" for files that were not,
while still printing a guarantee. It surfaced on the deployment host, which runs
``en_US.UTF-8``; the development machine does not, which is why every local run
was clean.

The behavioural test below does not depend on any locale being installed. It
demonstrates the actual failure mode — ``comm`` given unsorted input silently
missing a shared line — which is the property that makes the locale question
matter in the first place.
"""

from __future__ import annotations

import subprocess

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCRIPT = REPO_ROOT / "bin" / "compose.sh"


@pytest.fixture(scope="module")
def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_sort_is_pinned_to_byte_order(source: str) -> None:
    assert "LC_ALL=C sort" in source, "env keys are sorted with locale collation"


def test_comm_is_pinned_to_byte_order(source: str) -> None:
    assert "LC_ALL=C comm" in source, "the overlap comparison runs under locale collation"


def test_no_unpinned_sort_or_comm_remains(source: str) -> None:
    """One pinned call and one unpinned call is the same bug with extra steps."""
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for tool in ("sort", "comm"):
            if f"| {tool}" in stripped or stripped.startswith(f"{tool} "):
                assert f"LC_ALL=C {tool}" in stripped, f"unpinned {tool}: {stripped}"


def test_comm_given_unsorted_input_misses_a_real_overlap() -> None:
    """Guard the guard: why the ordering is not a cosmetic complaint.

    Both files contain ``ALPHA``. Sorted, ``comm -12`` reports it. With the left
    file out of order it reports *nothing at all*, because comm walks both
    inputs in lockstep and advances past the match. The disjointness check would
    have concluded the two files share no variables.

    The ordering matters, not merely the presence of a shared line: an earlier
    version of this test used a shared line that happened to sit first in both
    files, where comm finds it regardless and the point is not demonstrated.
    """
    right = "ALPHA\nZULU\n"

    def overlap(left: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", f"LC_ALL=C comm -12 <(printf %s '{left}') <(printf %s '{right}')"],
            capture_output=True,
            text=True,
            check=False,
        )

    found = overlap("ALPHA\nGAMMA\n")
    assert found.stdout.split() == ["ALPHA"], "the sorted case does not detect the overlap"

    missed = overlap("GAMMA\nALPHA\n")
    assert missed.stdout.split() == [], (
        "comm now detects overlaps in unsorted input; this test's premise needs revisiting"
    )
    assert "not in sorted order" in missed.stderr, "comm no longer warns about unsorted input"


def test_the_real_key_sets_are_still_disjoint_under_byte_order() -> None:
    """The check itself, against the files the wrapper actually compares."""
    generated = REPO_ROOT / ".generated" / "fixture-alpha-dev" / "compose.env"
    versions = REPO_ROOT / "versions.env"
    if not generated.exists():
        pytest.skip("fixtures are not rendered in this working tree")

    def keys(path) -> set[str]:
        return {
            line.split("=", 1)[0]
            for line in path.read_text(encoding="utf-8").splitlines()
            if "=" in line and line[:1].isupper()
        }

    assert not keys(generated) & keys(versions)
