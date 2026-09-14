"""Making a reading as the checkout's owner, when the test process is root.

**Two proofs needed this and one had it** (D1302). `test_honest_readers.py`
carried `_as_checkout_owner` and `_traversable_to_the_checkout_owner` from
D1165's repair; `test_render_atomicity.py` carried a bare
`skipif(os.geteuid() == 0)` for exactly the same reason and never learned about
either. The gate runs its static claim proofs as root, so that proof skipped on
every gate that could have recorded it, and `honest_readers` was `not_run` for
three sessions with both halves written -- a proof that skips under the identity
the gate runs as is a proof the gate can never record (D1121, both halves).

So the pair lives here, beside `outputs_chain.py` and `rendered_fixtures.py`,
which is where this directory keeps a helper two modules share. **Both moved
together, and that is not the plan's shape** (D1330): the re-entry alone is not
enough, because root's pytest temporary directory is `0700` and the child is
refused at an ancestor before it reaches the thing the proof made unreadable.

Nothing here is a fixture. A `conftest.py` would make these implicit, and an
implicit privilege change is the last thing either proof wants -- each says at
its call site that it is re-entering, and why.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT


def as_checkout_owner() -> list[str]:
    """The `sudo -u` prefix that puts a reading in D1060's position, or nothing.

    **D1155, and D1131's shape.** A refusal observed by reading through a
    directory the caller cannot traverse cannot be observed by root, which
    traverses everything. The proofs that do this used to carry
    `skipif(os.geteuid() == 0)`, and the gate runs its static claim proofs as
    root: they skipped on every gate that could have recorded them.

    So under root the reading is made as the checkout's OWNER, which is the user
    `op` is after a deploy. Unprivileged, nothing is prefixed and the reading is
    made directly.
    """
    if os.geteuid() != 0:
        return []
    owner = REPO_ROOT.stat()
    if owner.st_uid == 0:
        pytest.skip(
            f"{REPO_ROOT} is root-owned, so there is no unprivileged checkout owner to "
            "make the reading as (D1121/D1155); chown the checkout to the operator first"
        )
    return ["sudo", "-n", "-u", f"#{owner.st_uid}", "-g", f"#{owner.st_gid}"]


def traversable_to_the_checkout_owner(leaf: Path) -> None:
    """Let the checkout's owner reach `leaf`, when this process is root (D1300).

    D1165's repair re-enters as that owner so these proofs run under the
    identity the gate uses, and root's pytest temp directory is `0700` -- so
    without this the re-entry is refused at an ANCESTOR and never reaches the
    directory a proof made unreadable. Their first execution in any environment
    said so exactly: `Permission denied: '/tmp/pytest-of-root/…/.generated'`,
    which is `.generated` and not the project inside it, and a bare
    `PermissionError` there is D1151's shape rather than the reader's refusal.

    Ancestors only, and only under the temporary directory: what a proof makes
    unreadable it makes unreadable itself, and this must not reach it. A no-op
    unprivileged, where the owner is already the user running the test.
    """
    if os.geteuid() != 0:
        return
    temporary = Path(tempfile.gettempdir()).resolve()
    probe = leaf.resolve()

    # **Stop BEFORE the temporary root** (D1301). `is_relative_to` is true of a
    # path against itself, so a loop that only asks "is this under /tmp" walks
    # onto /tmp and chmods it -- which this did, as root, on the deployment
    # host: `0755` on a shared directory, sticky bit and world-write gone, and
    # every unprivileged write to /tmp refused until it was restored to `1777`.
    # The root is excluded by name, not by the shape of the condition.
    while probe != temporary and probe != probe.parent and probe.is_relative_to(temporary):
        probe.chmod(0o755)
        probe = probe.parent


def owned_by_the_checkout_owner(*paths: Path) -> None:
    """Give `paths` to the checkout's owner, when this process is root.

    **Traversability is not enough when the proof asserts an IDENTITY** (D1332).
    `traversable_to_the_checkout_owner` opens the ancestors so the re-entered
    child can reach the fixture; it leaves the fixture owned by root, because
    root created it. A proof that then asks *who owns this* gets `root` from a
    child running as the owner, and fails -- which is what the repaired
    atomicity proof did on its first execution as root, measured.

    So a proof whose subject is ownership hands the fixture over as well. A
    no-op unprivileged, where the files are already the caller's.
    """
    if os.geteuid() != 0:
        return
    owner = REPO_ROOT.stat()
    for path in paths:
        os.chown(path, owner.st_uid, owner.st_gid)


def python_for_the_owner() -> str:
    """The interpreter a re-entered child runs.

    The checkout's venv, because the child imports `agentic_postgres` and the
    system interpreter has no dependency installed. Named here rather than at
    each call site so a rig that has to substitute one -- the pinned image has
    no `.venv`, which is half of D1320 -- has a single thing to point at.
    """
    return str(REPO_ROOT / ".venv" / "bin" / "python")
