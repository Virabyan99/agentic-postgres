"""The backups reading, computed from what its producers PRINT (Session 41, D2501, D2512, D2540).

Session 40's backups surface read `could_not_determine` on every slot: the
reconciler handed `reconciler_dispatch.backups_reading` the block `bin/backup.sh
info --json` prints -- `backup_report.backup_state`, the deployed document's
closed `backup_state` block -- and the reading took `oldest_backup_stop` from
it, a key only `backup_report.summarise` returns. The two tests that fed the
surface handed it an already-shaped reading, so they shared the reader's belief
(CLAUDE.md §7 question 6).

These proofs cannot share it. Their input is **`slot3-prod`'s real `pgbackrest
--output=json info`** (Session 41's Sheet E0, `tests/fixtures/pgbackrest/
info-slot3-prod-2026-10.json`), passed through the producers' own functions --
`summarise`, then `backup_state` (what `info --json` prints) and `usage_block`
(what `usage --json` prints) -- and through JSON, which is what crosses the pipe
between `bin/backup.sh` and the reconciler. And a class guard reads which keys
the reading takes from each block and holds them to the keys its producer
returns, so the next reader of a key nobody prints fails here and not on a host.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, backup_report, reconciler_dispatch

pytestmark = [pytest.mark.contract, pytest.mark.p0]

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "pgbackrest" / "info-slot3-prod-2026-10.json"
STANZA = "slot3-prod"
#: A healthy archiver reading, `parse_archiver`'s shape (test_wal_archiving_signal's).
HEALTHY = {
    "archived_count": 5730,
    "last_archived_time": "2026-10-16 11:08:58.112949+00",
    "failed_count": 0,
    "last_failed_time": None,
    "last_failed_wal": None,
}
#: The newest attempt failed after the newest success.
BROKEN = {
    "archived_count": 5730,
    "last_archived_time": "2026-10-16 11:08:58.112949+00",
    "failed_count": 3,
    "last_failed_time": "2026-10-16 11:20:01.5+00",
    "last_failed_wal": "000000010000001600000082",
}


def _raw() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _printed(block: dict[str, Any]) -> dict[str, Any]:
    """What crosses the pipe: the producer's `json.dumps`, the reader's `json.loads`."""
    return json.loads(json.dumps(block, indent=2, sort_keys=True))


def _oldest_stop_from_the_raw_file() -> datetime:
    """Read independently of `summarise`: the minimum `timestamp.stop` of the
    stanza's backups, as pgBackRest wrote it."""
    (entry,) = [e for e in _raw() if e["name"] == STANZA]
    return datetime.fromtimestamp(min(b["timestamp"]["stop"] for b in entry["backup"]), UTC)


def test_the_window_comes_from_the_producers_real_output() -> None:
    summary = backup_report.summarise(_raw(), STANZA)
    reading = reconciler_dispatch.backups_reading(
        STANZA,
        info=_printed(backup_report.backup_state(summary, HEALTHY)),
        usage=_printed(backup_report.usage_block(summary, STANZA)),
        archiver=HEALTHY,
        mirror=None,
        sleeping=False,
    )
    # The oldest kept set's stop PLUS ONE SECOND (D2465), from the real file.
    expected = _oldest_stop_from_the_raw_file() + timedelta(seconds=1)
    assert expected == datetime(2026, 10, 12, 10, 39, 27, tzinfo=UTC)
    assert reading["earliest"] is not None, "the window's start was not read (D2501)"
    assert datetime.fromisoformat(reading["earliest"]) == expected
    assert reading["repository_status"] == "ok"
    assert reading["last_full_at"] == "2026-10-12T10:39:26Z"
    assert reading["latest"] is not None


def _keys_read_from(function: Any, parameter: str) -> set[str]:
    """Every string key `function` reads from `parameter` -- `p.get("k")`,
    `(p or {}).get("k")` and `p["k"]` -- by its AST."""

    def names_parameter(node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id == parameter
        if isinstance(node, ast.BoolOp):
            return any(names_parameter(value) for value in node.values)
        return False

    keys: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(function).lstrip())):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and names_parameter(node.func.value)
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            keys.add(str(node.args[0].value))
        if (
            isinstance(node, ast.Subscript)
            and names_parameter(node.value)
            and isinstance(node.slice, ast.Constant)
        ):
            keys.add(str(node.slice.value))
    return keys


def test_every_key_the_reading_takes_is_printed() -> None:
    """The class guard (D600, D2512): a key the reading takes from a printed
    block is a key that block's producer returns. Read from both functions, so
    a reader of a dropped key -- D2501's exact shape -- fails offline."""
    summary = backup_report.summarise(_raw(), STANZA)
    printed = {
        "info": set(backup_report.backup_state(summary, HEALTHY)),
        "usage": set(backup_report.usage_block(summary, STANZA)),
    }
    for parameter, produced in printed.items():
        taken = _keys_read_from(reconciler_dispatch.backups_reading, parameter)
        assert taken, f"the guard found no key read from {parameter!r}: the reader moved"
        missing = taken - produced
        assert not missing, (
            f"backups_reading reads {sorted(missing)} from {parameter!r}, which its producer "
            "never prints (D2501)"
        )
    assert "oldest_backup_stop" in _keys_read_from(reconciler_dispatch.backups_reading, "usage")
    # And the window's key stays OUT of the deployed document's closed block.
    assert "oldest_backup_stop" not in printed["info"]


def _reconciler() -> Any:
    spec = importlib.util.spec_from_file_location(
        "apg_reconciler_backups", REPO_ROOT / "bin" / "reconciler.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _completed(argv: list[str], code: int, stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, code, stdout=stdout, stderr="")


@pytest.mark.parametrize(
    ("info_exit", "expected"),
    [(backup_report.INFO_FAILING_EXIT, "problem"), (5, "unknown")],
    ids=["failing-is-a-problem", "control-an-unreadable-exit-is-unknown"],
)
def test_a_failing_repository_is_a_problem_not_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, info_exit: int, expected: str
) -> None:
    """`bin/backup.py info --json` prints its block for a failing repository and
    exits INFO_FAILING_EXIT. The reconciler parses it there as on 0, so the
    reading says `problem`; an exit that carries no block stays `unknown`."""
    reconciler = _reconciler()
    summary = backup_report.summarise(_raw(), STANZA)
    failing = _printed(backup_report.backup_state(summary, BROKEN))
    assert failing["status"] == backup_report.STATUS_FAILING

    def quiet(argv: list[str], timeout: int) -> subprocess.CompletedProcess:
        if argv[-2:] == ["info", "--json"]:
            return _completed(argv, info_exit, json.dumps(failing))
        if argv[-2:] == ["usage", "--json"]:
            return _completed(argv, 0, json.dumps(backup_report.usage_block(summary, STANZA)))
        return _completed(argv, 0, "true\n")  # the database container is running

    monkeypatch.setattr(reconciler, "_quiet", quiet)
    monkeypatch.setattr(reconciler, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(reconciler, "mirror_of", lambda key, document: None)
    monkeypatch.setattr(
        reconciler.container_exec, "run", lambda *argv, **kwargs: _completed(list(argv), 1)
    )
    document = {"database": {"container": "apg-slot3-prod-postgres-1", "name": "slot3_prod"}}
    reading = reconciler.backups_of(STANZA, document)
    assert reading["repository_status"] == expected
    assert reading["earliest"] is not None  # the window comes from `usage`, either way


def test_a_sleeping_slot_is_read_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    """D2541: the sleeping branch hands `mirror=None`, and the reading took
    `.detail` of it -- an AttributeError out of `record_backups` and out of the
    reconciler's loop, on every backups pass while any slot slept. Driven through
    `backups_of`'s own branch: the container reads `false`, and no backup child
    may be asked."""
    reconciler = _reconciler()
    asked: list[list[str]] = []

    def quiet(argv: list[str], timeout: int) -> subprocess.CompletedProcess:
        asked.append(argv)
        return _completed(argv, 0, "false\n")  # the database container is stopped

    monkeypatch.setattr(reconciler, "_quiet", quiet)
    document = {"database": {"container": "apg-slot3-prod-postgres-1", "name": "slot3_prod"}}
    reading = reconciler.backups_of(STANZA, document)
    assert reading["sleeping"] is True
    assert reading["earliest"] is None and reading["latest"] is None
    assert reading["mirror_status"] == "unknown"
    assert len(asked) == 1, f"a sleeping slot's backups were asked for: {asked[1:]}"
