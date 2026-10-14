"""One promotion bound for every restore that waits on recovery, and a drill's own document.

D2492: beta's PITR drill on OVH (1.18.0, 2026-10-14) was still replaying WAL when
`bin/restore-test.py`'s 900 s bound -- "chosen rather than measured" -- ran out,
and the two drills that promoted took 819 s and 772 s. `bin/restore.py` carried
the same literal, so a real restore of a busy day would have refused the same
way. The bound is now `restore_drill.PROMOTION_TIMEOUT_SECONDS`, read by both;
the guard is the CLASS -- no command defines its own promotion literal -- not the
one field that failed.

D2493: the PITR fixture took the newest drill document in the directory, so a
drill that wrote none was judged by an earlier drill's restored instance ("the
drill owner sees '1' note(s)" -- another drill's owner). `drill_document` returns
the document named by the id THIS drill printed, or None.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT, restore_drill

pytestmark = [pytest.mark.contract, pytest.mark.p0]

BIN = REPO_ROOT / "bin"
RECOVERY = REPO_ROOT / "tests" / "recovery"

#: The two commands that wait for a restored instance to promote on the shared bound.
SHARED_READERS = ("restore.py", "restore-test.py")

#: A promotion bound of its own, and why it may keep one: a branch's restore runs
#: as a reconciler child whose whole budget is `CHILD_SECONDS["branch-runtime.sh"]`
#: (`bin/reconciler.py`), so its bound must sit INSIDE that budget (D2495).
OWN_BOUND = {"branch-runtime.py": "PROMOTION_SECONDS"}

#: The live proofs that run `bin/restore-test.sh` and read its document.
DRILL_PROOFS = (
    "test_future_pitr.py",
    "test_session32_workflow_restore.py",
    "test_session34_delivery_restore.py",
)


def _module_assignments(path: Path) -> dict[str, ast.expr]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node.value
    return found


def _names_shared_bound(expression: ast.expr) -> bool:
    return any(
        isinstance(node, ast.Attribute)
        and node.attr == "PROMOTION_TIMEOUT_SECONDS"
        and isinstance(node.value, ast.Name)
        and node.value.id == "restore_drill"
        for node in ast.walk(expression)
    )


def test_the_shared_bound_outlasts_the_slowest_promotion_measured() -> None:
    # 819 s is the slowest promotion beta measured (D2492); a bound that is not
    # well above it is the 900 s literal again.
    assert restore_drill.PROMOTION_TIMEOUT_SECONDS >= 4 * 819


def test_the_restore_commands_read_the_shared_bound() -> None:
    for name in SHARED_READERS:
        value = _module_assignments(BIN / name).get("PROMOTION_TIMEOUT_SECONDS")
        assert value is not None, f"bin/{name} no longer defines PROMOTION_TIMEOUT_SECONDS"
        assert _names_shared_bound(value), (
            f"bin/{name} sets its own promotion bound ({ast.unparse(value)}) instead of "
            "restore_drill.PROMOTION_TIMEOUT_SECONDS (D2492)"
        )


def test_no_command_defines_a_promotion_literal_of_its_own() -> None:
    scanned = 0
    for path in sorted(BIN.glob("*.py")):
        scanned += 1
        for name, value in _module_assignments(path).items():
            if "PROMOTION" not in name:
                continue
            literal = isinstance(value, ast.Constant) and isinstance(value.value, (int, float))
            if not literal:
                continue
            assert OWN_BOUND.get(path.name) == name, (
                f"bin/{path.name}: {name} = {value.value} is a promotion bound of its own; "
                "read restore_drill.PROMOTION_TIMEOUT_SECONDS (D2492)"
            )
    assert scanned > 50, f"the scan read {scanned} commands; it is not reading bin/"


def test_a_branch_promotion_bound_sits_inside_its_reconciler_budget() -> None:
    bound = _module_assignments(BIN / "branch-runtime.py")["PROMOTION_SECONDS"]
    assert isinstance(bound, ast.Constant)
    children = _module_assignments(BIN / "reconciler.py")["CHILD_SECONDS"]
    assert isinstance(children, ast.Dict)
    budget = {
        key.value: value.value
        for key, value in zip(children.keys, children.values, strict=True)
        if isinstance(key, ast.Constant) and isinstance(value, ast.Constant)
    }
    assert bound.value < budget["branch-runtime.sh"], (
        f"branch-runtime's promotion bound {bound.value} s does not fit its reconciler "
        f"child budget {budget['branch-runtime.sh']} s"
    )


def test_every_drill_proof_outlasts_the_drill_and_reads_its_own_document() -> None:
    for name in DRILL_PROOFS:
        path = RECOVERY / name
        value = _module_assignments(path).get("DRILL_TIMEOUT_SECONDS")
        assert value is not None and _names_shared_bound(value), (
            f"{name}: DRILL_TIMEOUT_SECONDS is not derived from the drill's own bound, so "
            "the proof's kill can arrive before the command's refusal (D2492)"
        )
        text = path.read_text(encoding="utf-8")
        assert "restore_drill.drill_document(" in text, f"{name} does not read its own document"
        assert "st_mtime" not in text, f"{name} still picks a drill document by mtime (D2493)"


def _write(directory: Path, key: str, drill_id: str) -> Path:
    path = directory / f"restore-drill-{key}-{drill_id}.json"
    path.write_text("{}\n", encoding="utf-8")
    return path


def test_the_document_is_the_one_this_drill_named(tmp_path: Path) -> None:
    _write(tmp_path, "beta-dev", "20261012133886b8")
    mine = _write(tmp_path, "beta-dev", "2026101420156612")
    stdout = "restore-test: drill 2026101420156612 for beta-dev\n  live volume  v\n"
    assert restore_drill.drill_document(tmp_path, stdout) == mine


def test_a_drill_that_wrote_nothing_has_no_document_even_beside_an_older_one(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "beta-dev", "20261012133886b8")
    stdout = "restore-test: drill 2026101420156612 for beta-dev\n"
    assert restore_drill.drill_document(tmp_path, stdout) is None


def test_no_or_two_drill_lines_name_no_document(tmp_path: Path) -> None:
    _write(tmp_path, "beta-dev", "2026101420156612")
    assert restore_drill.drill_document(tmp_path, "") is None
    two = (
        "restore-test: drill 2026101420156612 for beta-dev\n"
        "restore-test: drill 2026101420156612 for beta-dev\n"
    )
    assert restore_drill.drill_document(tmp_path, two) is None
