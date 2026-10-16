"""The reconciler's usage sampler (Session 41, ADR 0275, D2523).

Every 300 s the reconciler takes one sample per deployed slot, each figure read
the way `doctor usage` reads it -- the functions moved to
`agentic_postgres.usage_reading` so the two cannot differ -- and hands it to
`control_record_usage`. **A figure that cannot be read is NULL and named in
`unread`, never a zero** (ADR 0195); "no customer backend" is a reading of none
present, quiet and READ (Sheet E0, D2539); a sleeping project is sampled as
sleeping without a container read. Agent calls and workflow runs are counted
from their durable rows since the previous sample, never from the per-process
`agent_tool_calls_total` a recreated `mcp` resets (D1609, D1643).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from collections.abc import Iterator
from typing import Any

import control_cluster as cc
import pytest

from agentic_postgres import REPO_ROOT, naming, reconciler_dispatch, usage_reading

pytestmark = [pytest.mark.contract, pytest.mark.p0]

KEY = "slot5-prod"
DOCUMENT = {"database": {"container": f"apg-{KEY}-postgres-1", "name": "slot5_prod"}}
SINCE = "2026-10-16 17:00:00.123456+00"
NOW = "2026-10-16 17:05:00.654321+00"


def _reconciler() -> Any:
    spec = importlib.util.spec_from_file_location(
        "apg_reconciler_usage", REPO_ROOT / "bin" / "reconciler.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Containers:
    """`container_exec.run`'s stand-in: each read answered by what it asks."""

    def __init__(self, *, store_up: bool = True, backends: str = "0|") -> None:
        self.store_up = store_up
        self.backends = backends
        self.asked: list[str] = []

    def __call__(self, container: str, *argv: str, **kwargs: Any) -> Any:
        text = " ".join(argv)
        self.asked.append(text)
        if argv[0] == "wget":
            if not self.store_up:
                return subprocess.CompletedProcess(argv, 1, "", "wget: connection refused")
            series = [{"metric": {"project": KEY}, "value": [0, "57"]}]
            body = {"status": "success", "data": {"result": series}}
            return subprocess.CompletedProcess(argv, 0, json.dumps(body), "")
        if "pg_database_size" in text:
            return subprocess.CompletedProcess(argv, 0, "10548927\n", "")
        if "pg_stat_activity" in text:
            return subprocess.CompletedProcess(argv, 0, self.backends + "\n", "")
        if "app_private.agent_audit" in text:
            # The window's counts only when the statement names a `since`.
            window = "3|1" if "started_at > '" in text else "|"
            return subprocess.CompletedProcess(argv, 0, f"{window}|12|{NOW}\n", "")
        return subprocess.CompletedProcess(argv, 1, "", "unexpected")


@pytest.fixture
def sampled(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Any:
    reconciler = _reconciler()
    monkeypatch.setattr(reconciler, "BRANCH_ROOT", tmp_path / "branches")
    monkeypatch.setattr(
        reconciler, "_quiet",
        lambda argv, timeout: subprocess.CompletedProcess(argv, 0, "true\n", ""),
    )  # fmt: skip
    return reconciler


def test_each_figure_is_read_or_named_unread(sampled: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """With the store down, the request counter is NULL and named -- not 0 --
    while every figure that was read is its value; no customer backend reads as
    quiet and is NOT unread; the repository's size comes from the backups
    pass's block; the first sample counts no calls (named), the next counts
    them from `since`."""
    containers = Containers(store_up=False)
    monkeypatch.setattr(sampled.container_exec, "run", containers)
    sample, since, today = sampled.usage_of(KEY, DOCUMENT, None, {"repository_bytes": 6398256})
    assert sample["state"] == "active"
    assert (sample["database_bytes"], sample["repository_bytes"]) == (10548927, 6398256)
    assert (sample["customer_connections"], sample["last_customer_activity"]) == (0, None)
    assert sample["requests_counter"] is None
    assert (
        "requests_counter" in sample["unread"] and "last_customer_activity" not in sample["unread"]
    )
    assert {"agent_calls", "workflow_runs"} <= set(sample["unread"])
    assert "requests_counter: the store did not answer the query" in sample["reason"]
    assert (since, today) == (NOW, 12)
    again, _, _ = sampled.usage_of(KEY, DOCUMENT, since, None)
    assert (again["agent_calls"], again["workflow_runs"]) == (3, 1)
    assert "repository_bytes" in again["unread"], "a missing block is unread, never zero"
    monkeypatch.setattr(sampled.container_exec, "run", Containers(store_up=True))
    read, _, _ = sampled.usage_of(KEY, DOCUMENT, since, None)
    assert read["requests_counter"] == 57 and "requests_counter" not in read["unread"]


def test_a_sleeping_project_is_sampled_as_sleeping(
    sampled: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The database container reads `false`: the sample says so, every figure is
    unread with one reason, and no container is asked anything."""
    containers = Containers()
    monkeypatch.setattr(sampled.container_exec, "run", containers)
    monkeypatch.setattr(
        sampled, "_quiet", lambda argv, timeout: subprocess.CompletedProcess(argv, 0, "false\n", "")
    )
    sample, since, today = sampled.usage_of(KEY, DOCUMENT, SINCE, {"repository_bytes": 1})
    assert sample["state"] == "sleeping" and sample["reason"] == "the project sleeps"
    assert sample["unread"] == list(reconciler_dispatch.USAGE_FIGURES)
    assert all(sample[f] is None for f in reconciler_dispatch.USAGE_FIGURES)
    assert (since, today) == (None, None) and containers.asked == []


def test_a_customer_backend_is_activity(sampled: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """One customer backend: counted, and its newest moment is the activity."""
    monkeypatch.setattr(
        sampled.container_exec, "run", Containers(backends="1|2026-10-16 17:04:00+00")
    )
    sample, _, _ = sampled.usage_of(KEY, DOCUMENT, SINCE, None)
    assert (sample["customer_connections"], sample["last_customer_activity"]) == (
        1, "2026-10-16 17:04:00+00",
    )  # fmt: skip


@pytest.fixture(scope="module")
def cluster() -> Iterator[cc.ControlCluster]:
    try:
        with cc.control_cluster() as started:
            yield started
    except RuntimeError as error:
        pytest.skip(str(error))


def test_calls_are_counted_from_durable_rows(cluster: cc.ControlCluster) -> None:
    """The counts read `app_private.agent_audit` and `app_private.workflow_run`
    by time -- never the per-process series -- and the statement runs against
    the release's own tables (the control cluster carries them), returning the
    four fields the sampler parses; `since` is checked before it is used."""
    statement = usage_reading.durable_counts_sql(SINCE)
    assert "app_private.agent_audit" in statement and "app_private.workflow_run" in statement
    assert "agent_tool_calls_total" not in statement
    (row,) = cluster.query(statement)
    fields = row.split("|")
    assert len(fields) == 4 and fields[0] == "0" and fields[1] == "0", fields
    assert usage_reading.INSTANT.match(fields[3]), fields[3]
    first = cluster.query(usage_reading.durable_counts_sql(None))[0].split("|")
    assert first[:2] == ["", ""] and first[2].isdigit()
    with pytest.raises(ValueError):
        usage_reading.durable_counts_sql("'; DROP TABLE x; --")
    assert "agent_tool_calls_total" not in usage_reading.REQUESTS_BELOW_400_QUERY


def test_the_activity_reader_reads_only_the_customer_roles() -> None:
    """The backends counted are the project's two customer roles -- derived
    names -- and nothing else; a name that is not one is refused."""
    roles = naming.database_roles(naming.sql_key(KEY))
    statement = usage_reading.activity_sql((roles["customer_app"], roles["customer_admin"]))
    assert f"'{roles['customer_app']}'" in statement and f"'{roles['customer_admin']}'" in statement
    for role in ("authenticator", roles["auth_service"]):
        assert f"'{role}'" not in statement
    with pytest.raises(ValueError):
        usage_reading.activity_sql(("x'); --", roles["customer_admin"]))


def test_the_sample_interval_is_the_one_the_idle_rule_counts() -> None:
    """The control set's idle rule counts its window in 300 s samples (0008);
    the reconciler samples every USAGE_SAMPLE_SECONDS. The two are one fact."""
    template = (
        REPO_ROOT / "projects" / "control" / "migrations" / "templates"
        / "0008-control-plans-usage.sql"
    ).read_text(encoding="utf-8")  # fmt: skip
    assert "idle_sleep_minutes * 60 / 300.0" in template
    assert _reconciler().USAGE_SAMPLE_SECONDS == 300


def test_a_limit_notice_passes_at_80_percent() -> None:
    """`storage_gb` against the database's bytes, `agent_calls_per_day` against
    the day's calls: each passes at 80% of Free's number and not before; a
    figure not read passes nothing."""
    sample = {"database_bytes": 4 * 10**9}
    assert reconciler_dispatch.limit_notices(sample, 8000, "free") == [
        "storage_gb", "agent_calls_per_day",
    ]  # fmt: skip
    assert reconciler_dispatch.limit_notices({"database_bytes": 4 * 10**9 - 1}, 7999, "free") == []
    assert reconciler_dispatch.limit_notices({"database_bytes": None}, None, "free") == []


def test_the_sampler_never_reads_the_per_process_series(
    sampled: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D1643, through the sampler itself: its agent calls are the durable
    rows' count since the previous sample (3 here), and nothing it asks the
    store names `agent_tool_calls_total` -- the series a recreated `mcp` resets."""
    containers = Containers()
    monkeypatch.setattr(sampled.container_exec, "run", containers)
    sample, _, _ = sampled.usage_of(KEY, DOCUMENT, SINCE, None)
    assert sample["agent_calls"] == 3
    asked_store = [text for text in containers.asked if text.startswith("wget")]
    assert asked_store, "the store was not asked at all"
    assert not any("agent_tool_calls" in text for text in asked_store), asked_store
