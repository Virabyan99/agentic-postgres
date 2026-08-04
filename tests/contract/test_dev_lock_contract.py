"""``--update`` and ``--check`` must be the same resolution.

``bin/lock-dev-deps.sh --check`` verifies the committed lock is exactly what
``--update`` would produce. That sentence is the contract, and it was false.

``uv pip compile`` reads an existing ``--output-file`` and treats its pins as
preferences. ``--update`` compiled onto the live lock, so it resolved to what was
already pinned and rewrote the file unchanged; ``--check`` compiled into a fresh
temp file, so it resolved to what is currently on the index. The moment any
transitive dependency published a release, the two disagreed forever: ``--check``
failed, ``--update`` reported "wrote" and changed nothing, and the instruction
``--check`` printed was the one thing that could not fix it.

The failure is quiet in the worst way — both commands exit as if they worked —
and it only appears once upstream moves, which is to say on a day unrelated to
whatever change is being blamed.
"""

from __future__ import annotations

import re

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCRIPT = REPO_ROOT / "bin" / "lock-dev-deps.sh"


@pytest.fixture(scope="module")
def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_only_one_function_invokes_uv_pip_compile(source: str) -> None:
    """Two call sites are two resolutions, which is how they drifted apart."""
    assert source.count("uv pip compile") == 1


def test_update_does_not_compile_onto_the_live_lock(source: str) -> None:
    """The defect itself: `compile_to "${LOCK_FILE}"` makes the lock its own input."""
    assert 'compile_to "${LOCK_FILE}"' not in source, (
        "--update compiles onto the file it is replacing, so uv prefers the pins already there"
    )


def test_both_modes_compile_into_a_temporary_destination(source: str) -> None:
    destinations = set(re.findall(r'compile_to "\$\{(\w+)\}"', source))
    assert destinations, "no compile_to call sites found; the search pattern is stale"
    assert destinations <= {"staged", "tmp"}, (
        f"compile_to is called with a non-temporary destination: {sorted(destinations)}"
    )


def test_the_staged_file_is_cleaned_up_on_exit(source: str) -> None:
    """A leaked temp file with a full dependency lock in it is avoidable litter."""
    update_body = source.split("--update)", 1)[1].split(";;", 1)[0]
    assert "trap" in update_body and "rm -f" in update_body
