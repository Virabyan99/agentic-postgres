"""Monitoring is a list of readings that each name their source (Session 42, ADR 0279).

Read against the control set's own migrations: every signal names a column that
exists, no two signals read one column, and `app.control_project_monitoring`
reads no table outside the signals' and serves exactly the signals' names.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import signals

pytestmark = [pytest.mark.contract, pytest.mark.p0]

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = sorted((REPO_ROOT / "projects/control/migrations/templates").glob("*.sql"))
SQL = "\n".join(path.read_text(encoding="utf-8").split("-- migrate:down")[0] for path in TEMPLATES)


def _columns(table: str) -> set[str]:
    """A control table's columns: its CREATE TABLE block and every ADD COLUMN."""
    block = re.search(rf"CREATE TABLE app\.{table} \((.*?)\n\);", SQL, re.S)
    assert block, f"no CREATE TABLE app.{table}"
    columns = {m.group(1) for m in re.finditer(r"^\s+([a-z_]+)\s+[a-z]", block.group(1), re.M)}
    for alter in re.finditer(rf"ALTER TABLE app\.{table}\b(.*?);", SQL, re.S):
        columns |= set(re.findall(r"ADD COLUMN\s+([a-z_]+)", alter.group(1)))
    return columns - {"primary", "unique", "check", "constraint"}


def _monitoring_body() -> str:
    text = (
        REPO_ROOT / "projects/control/migrations/templates/0009-control-insights.sql"
    ).read_text("utf-8")
    start = text.index("FUNCTION app.control_project_monitoring(")
    body = text.index("AS $$", start)
    return text[body : text.index("$$;", body + 5)]


def test_every_signal_names_a_source_that_exists() -> None:
    """Each `source` is `app.<table>.<column>` and the column exists in the
    control set's migrations (the CREATE TABLE or an ADD COLUMN) -- ten at most."""
    assert 0 < len(signals.SIGNALS) <= 10
    for signal in signals.SIGNALS:
        schema, table, column = signal.source.split(".")
        assert schema == "app", signal
        assert column in _columns(table), f"{signal.name}: {signal.source} names no column"


def test_no_two_signals_read_one_column() -> None:
    """One source per signal and one signal per source (D704): a column read
    twice is a second answer to one question."""
    sources = [signal.source for signal in signals.SIGNALS]
    names = [signal.name for signal in signals.SIGNALS]
    assert len(set(sources)) == len(sources), sources
    assert len(set(names)) == len(names), names


def test_the_monitoring_function_reads_only_the_named_tables() -> None:
    """The function reads no `app.control_*` table but the signals' own; the
    functions it calls are the membership checks and the usage document (which
    reads the usage samples); and the signal names it builds are exactly the
    table's -- so a signal can neither be served from elsewhere nor dropped."""
    body = _monitoring_body()
    referenced = set(re.findall(r"app\.(control_[a-z_]+)", body))
    called = {"control_enter", "control_require_role", "control_project_organization",
              "control_usage_document"}  # fmt: skip
    tables = {signal.source.split(".")[1] for signal in signals.SIGNALS}
    assert referenced - called == tables, sorted(referenced - called)
    # The names built one by one, and the gauges built by the FOREACH loop.
    built = set(re.findall(r"'([a-z_]+)', (?:CASE|jsonb_build_object)", body))
    loop = re.search(r"FOREACH v_figure IN ARRAY ARRAY\[(.*?)\]", body, re.S)
    assert loop, "the gauges' loop moved"
    built |= set(re.findall(r"'([a-z_]+)'", loop.group(1)))
    assert built == set(signals.BY_NAME), sorted(built ^ set(signals.BY_NAME))
