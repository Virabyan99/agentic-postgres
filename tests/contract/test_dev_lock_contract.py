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
    """Every destination is a variable this script assigned from ``mktemp``.

    **Replaced by a stricter form, authorised by ADR 0176.** This asserted
    ``destinations <= {"staged", "tmp"}`` -- a list of the two names that
    happened to exist when it was written -- and went red the moment ``--check``
    needed a second temporary, to hold the body before the cutoff line is
    stamped onto it. The claim it makes is about a *construct*: the destination
    is a temp file. It was standing a *name* in for that, which is D464's family,
    and the failure mode is the one that matters -- **the safe change is what
    broke it, while an unsafe destination named `tmp` would have walked straight
    through.**

    Widening the list to the measured set is permitted by §6 and would have left
    the proxy in place to break at the next temporary.

    **EVERY assignment is checked, not merely that one of them is a `mktemp`**,
    and the mutation battery is why. The first draft asked whether the
    destination's name appeared in some `mktemp` assignment somewhere in the
    file, and a mutation that reassigned `tmp` to `"${LOCK_FILE}.partial"`
    immediately before the call **survived it**: the earlier `tmp="$(mktemp)"`
    was still there to satisfy the membership test. That is the defect this
    module exists for, reintroduced under a guard written against it.
    """
    destinations = set(re.findall(r'compile_to "\$\{(\w+)\}"', source))
    assert destinations, "no compile_to call sites found; the search pattern is stale"

    assignments: dict[str, list[str]] = {}
    for name, value in re.findall(r"^\s*(\w+)=(.+)$", source, re.MULTILINE):
        assignments.setdefault(name, []).append(value.strip())
    assert assignments, "no assignment found at all; the search pattern is stale"

    offenders = [
        f"{name}={value}"
        for name in sorted(destinations)
        for value in assignments.get(name, ["<never assigned>"])
        if value != '"$(mktemp)"'
    ]
    assert not offenders, (
        "compile_to's destination is assigned something other than a fresh "
        f"temporary file: {offenders}"
    )


def test_the_staged_file_is_cleaned_up_on_exit(source: str) -> None:
    """A leaked temp file with a full dependency lock in it is avoidable litter."""
    update_body = source.split("--update)", 1)[1].split(";;", 1)[0]
    assert "trap" in update_body and "rm -f" in update_body
