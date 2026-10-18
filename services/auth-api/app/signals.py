"""Monitoring is a list of readings that each name their source (Session 42, ADR 0279).

Every signal a customer is shown about a project's health is a reading the
control database already holds -- a usage sample (ADR 0275, ADR 0278), the
backups reading (ADR 0273), an insight sample (ADR 0278) -- and this table names
which one, by table and column. `app.control_project_monitoring` reads exactly
these and nothing else; `GET /v1/projects/{key}/monitoring` serves each with its
value, its `observed_at` and its source, or `unread` with the reason. No new
reader, no new sample, no threshold, no colour, no alert (ADR 0279).

Guarded by `tests/contract/test_signals.py`: every source column exists in the
control set's migrations, no two signals read one column, and the function's
signals are exactly these names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Signal:
    name: str
    unit: str
    #: `<table>.<column>`: where the value comes from, read back by a test.
    source: str
    description: str


SIGNALS: Final[tuple[Signal, ...]] = (
    Signal("state", "text", "app.control_usage_samples.state",
           "awake (active) or asleep (sleeping), from the newest usage sample"),
    Signal("database_bytes", "bytes", "app.control_usage_samples.database_bytes",
           "the database's size, from the newest sample that read it"),
    Signal("repository_bytes", "bytes", "app.control_usage_samples.repository_bytes",
           "the backup repository's size, from the newest sample that read it"),
    Signal("customer_connections", "count", "app.control_usage_samples.customer_connections",
           "your database roles' open connections, from the newest sample that read them"),
    Signal("requests_last_hour", "count", "app.control_usage_samples.requests_counter",
           "requests answered below 400 in the last hour, counted across resets"),
    Signal("db_time_last_hour", "milliseconds", "app.control_usage_samples.db_time_ms",
           "time your statements spent executing in the last hour, counted across resets"),
    Signal("backup_status", "text", "app.control_backup_readings.repository_status",
           "the backup repository's status at the last backups reading"),
    Signal("latest_recoverable_time", "instant", "app.control_backup_readings.latest",
           "the newest moment a restore can reach, at the last backups reading"),
    Signal("last_full_backup_at", "instant", "app.control_backup_readings.last_full_at",
           "when the newest full backup finished, at the last backups reading"),
    Signal("insights_sampled_at", "instant", "app.control_insight_samples.observed_at",
           "when your statements were last sampled for Query Insights"),
)  # fmt: skip

BY_NAME: Final[dict[str, Signal]] = {signal.name: signal for signal in SIGNALS}


def document(reading: dict) -> dict:
    """`control_project_monitoring`'s reading as the route serves it: each signal
    in this table's order, its unit and source beside the value the control
    database read -- or `unread` with its reason. A signal the reading did not
    carry is unread, never dropped (ADR 0195)."""
    values = reading.get("signals") or {}
    missing = {"value": None, "observed_at": None, "unread": "the control database did not read it"}
    out = []
    for signal in SIGNALS:
        read = values.get(signal.name) or missing
        item = {
            "name": signal.name,
            "unit": signal.unit,
            "source": signal.source,
            "description": signal.description,
            "value": read.get("value"),
            "observed_at": read.get("observed_at"),
        }
        if read.get("unread"):
            item["unread"] = read["unread"]
        out.append(item)
    return {"project_key": reading.get("project_key"), "read_at": reading.get("read_at"),
            "signals": out}  # fmt: skip
