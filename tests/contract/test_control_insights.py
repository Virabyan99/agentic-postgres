"""Query Insights in the control set (Session 42, ADR 0278, D2569, D2571).

The reconciler writes one insight sample per awake slot per usage pass through
`app.control_record_insights`, granted to nobody: the top statements of the
project's customer-facing roles, counters AS READ, the text normalised and cut
to 2000, older than 7 days deleted by the writer. A member reads
`control_project_insights`: per statement the INCREASE over the window with a
moved `stats_reset` or a decrease read as a reset (D553), its mean and ratios,
ordered by time -- numbers, never a finding, a recommendation, a confidence or
a severity; fewer than two samples is `could_not_determine`, never an empty
list (ADR 0195).
"""

# ruff: noqa: S608 -- every interpolated value is a uuid, a key or a number this module made.

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import control_cluster as cc
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

ADVICE = ("finding", "recommendation", "confidence", "severity")


@pytest.fixture(scope="module")
def cluster() -> Iterator[cc.ControlCluster]:
    try:
        with cc.control_cluster() as started:
            yield started
    except RuntimeError as error:
        pytest.skip(str(error))


class Project:
    """A viewer's adopted project, and its insight samples written directly
    (the writer's own proof is `test_no_role_but_the_reconciler_writes_a_sample`)."""

    def __init__(self, cluster: cc.ControlCluster) -> None:
        self.cluster = cluster
        tag = uuid.uuid4().hex[:8]
        self.user = str(uuid.uuid4())
        cluster.query(
            "INSERT INTO app.control_accounts (user_id, username, display_name) "
            f"VALUES ('{self.user}', 'i-{tag}', 'I')"
        )
        self.org = cluster.query(
            f"INSERT INTO app.control_organizations (name, created_by) VALUES ('i {tag}', "
            f"'{self.user}') RETURNING id"
        )[0]
        cluster.query(
            "INSERT INTO app.control_memberships (organization_id, user_id, role) "
            f"VALUES ('{self.org}', '{self.user}', 'viewer')"
        )
        self.key = f"i{tag}-prod"
        cluster.query(
            f"SELECT app.control_adopt_project('{self.key}', '{self.org}', 'i{tag}', 'prod', "
            f"'{self.key}.test', '1.20.0', 'abc')"
        )

    def row(self, minutes_ago: int, queryid: int, calls: int, ms: float, *, reset: str = "r1",
            role: str = "customer_app", rows: int = 0, hit: int = 0, read: int = 0,
            query: str = "SELECT name FROM app.items WHERE id = $1") -> None:  # fmt: skip
        stats_reset = f"'2026-10-18 00:00:00+00'::timestamptz + interval '{ord(reset[-1])} minutes'"
        self.cluster.query(
            "INSERT INTO app.control_insight_samples (project_key, observed_at, queryid, role, "
            "calls, total_exec_ms, rows, shared_blks_hit, shared_blks_read, query, stats_reset) "
            f"VALUES ('{self.key}', now() - interval '{minutes_ago} minutes', {queryid}, '{role}', "
            f"{calls}, {ms}, {rows}, {hit}, {read}, '{query}', {stats_reset})"
        )

    def insights(self, hours: int = 24, limit: int = 20) -> dict[str, Any]:
        (text,) = self.cluster.as_service(
            f"SELECT app.control_project_insights('{self.user}', '{self.key}', {hours}, {limit})"
        )
        return json.loads(text)


def test_a_reset_is_read_not_subtracted(cluster: cc.ControlCluster) -> None:
    """D553: calls 100 -> 150 -> (stats_reset moved) 30 -> 70 is +50, a reset
    counted from zero (+30), +40: 120 calls, never 70 - 100; time likewise
    (+500, +300, +400 = 1,200 ms); one reset counted. A statement's first sample
    in the window counts nothing (it may have entered the top 50 late)."""
    project = Project(cluster)
    for minutes, calls, ms, reset in ((20, 100, 1000.0, "r1"), (15, 150, 1500.0, "r1"),
                                      (10, 30, 300.0, "r2"), (5, 70, 700.0, "r2")):  # fmt: skip
        project.row(minutes, 7, calls, ms, reset=reset, rows=calls * 2, hit=calls * 9, read=calls)
    project.row(5, 8, 1000, 99999.0, reset="r2", query="SELECT 1 WHERE $1")
    document = project.insights()
    assert document["status"] == "read" and document["resets"] == 1, document
    (statement,) = document["statements"]
    assert (statement["calls"], statement["total_ms"]) == (120, 1200), statement
    assert (
        statement["mean_ms"] == 10 and statement["rows"] == 240 and statement["rows_per_call"] == 2
    )
    assert statement["shared_blks_read_per_call"] == 1 and statement["cache_hit_ratio"] == 0.9
    assert statement["role"] == "customer_app" and statement["query"].endswith("$1")


def test_no_member_advises(cluster: cc.ControlCluster) -> None:
    """The document states numbers and nothing that sounds like advice: no
    member, at any depth, named finding, recommendation, confidence or
    severity; one fixed `tuning` sentence pointing at `apg migrate propose`."""
    project = Project(cluster)
    project.row(10, 1, 10, 50.0)
    project.row(5, 1, 20, 90.0)
    document = project.insights()

    def keys(value: Any) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {k for v in value.values() for k in keys(v)}
        if isinstance(value, list):
            return {k for v in value for k in keys(v)}
        return set()

    assert not keys(document) & set(ADVICE), keys(document)
    assert document["tuning"] == (
        "To change a query plan, write a migration in your project's set and run "
        "apg migrate propose (docs/developer-guide.md)."
    )
    assert [s["calls"] for s in document["statements"]] == [10]


def test_an_empty_window_is_not_an_empty_list(cluster: cc.ControlCluster) -> None:
    """No sample in the window, and one sample (which cannot show an increase),
    are each `could_not_determine` with the reason and `statements` null --
    never `[]`, which would read as "no statement ran"."""
    project = Project(cluster)
    none = project.insights(hours=2)
    assert none["status"] == "could_not_determine" and none["statements"] is None, none
    assert none["samples"] == {"expected": 24, "present": 0}
    assert "no insight sample" in none["reason"]
    project.row(5, 1, 10, 50.0)
    one = project.insights(hours=2)
    assert one["status"] == "could_not_determine" and "two" in one["reason"], one


def test_a_foreign_and_a_missing_project_answer_alike(cluster: cc.ControlCluster) -> None:
    """THR-CTL-ENUMERATION's rule, THR-INS-LEAK: another organisation's
    project and a project that does not exist read the one `not_found`; a
    window outside 1..168 hours or a limit outside 1..50 is refused."""
    mine, theirs = Project(cluster), Project(cluster)
    foreign = cluster.refused(
        f"SELECT app.control_project_insights('{mine.user}', '{theirs.key}', 24, 20)"
    )
    missing = cluster.refused(
        f"SELECT app.control_project_insights('{mine.user}', 'nope-prod', 24, 20)"
    )
    assert "AP404: not_found" in foreign and "AP404: not_found" in missing, (foreign, missing)
    for hours, limit in ((0, 20), (169, 20), (24, 0), (24, 51)):
        assert "AP422" in cluster.refused(
            f"SELECT app.control_project_insights('{mine.user}', '{mine.key}', {hours}, {limit})"
        )


def test_no_role_but_the_reconciler_writes_a_sample(cluster: cc.ControlCluster) -> None:
    """The identity service's role can neither execute the writer nor touch
    the table; the writer, as the reconciler reaches it, records one row per
    statement, cuts the text to 2000, and refuses a member it does not know
    and more than 50 statements."""
    project = Project(cluster)
    (held,) = cluster.query(
        f"SELECT has_function_privilege('{cluster.auth_role}', "
        "'app.control_record_insights(jsonb)', 'EXECUTE')"
    )
    assert held == "f"
    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        (table,) = cluster.query(
            f"SELECT has_table_privilege('{cluster.auth_role}', 'app.control_insight_samples', "
            f"'{privilege}')"
        )
        assert table == "f", privilege
    statement = {
        "queryid": 42, "role": "customer_app", "calls": 3, "total_exec_ms": 1.5, "rows": 3,
        "shared_blks_hit": 9, "shared_blks_read": 1, "query": "SELECT $1" + " " * 2500 + "x",
    }  # fmt: skip
    sample = {"project_key": project.key, "stats_reset": None, "statements": [statement]}
    payload = json.dumps(sample).replace("'", "''")
    assert cluster.query(f"SELECT app.control_record_insights('{payload}'::jsonb)") == ["1"]
    (length,) = cluster.query(
        f"SELECT length(query) FROM app.control_insight_samples WHERE project_key = '{project.key}'"
    )
    assert length == "2000"
    for bad in (
        {**sample, "extra": 1},
        {**sample, "statements": [{**statement, "literal": "x"}]},
        {**sample, "statements": [statement] * 51},
    ):
        text = json.dumps(bad).replace("'", "''")
        assert (
            "AP422: invalid_samples"
            in cluster.run(f"SELECT app.control_record_insights('{text}'::jsonb)").stderr
        )


def test_samples_older_than_seven_days_are_removed_by_the_writer(
    cluster: cc.ControlCluster,
) -> None:
    """INSIGHT_KEEP_DAYS: the writer deletes the key's rows older than 7 days in
    its own transaction -- an 8-day-old row goes, a 6-day-old row stays, and
    another project's old row is not this write's to delete."""
    project, other = Project(cluster), Project(cluster)
    project.row(8 * 24 * 60, 1, 1, 1.0)
    project.row(6 * 24 * 60, 2, 1, 1.0)
    other.row(8 * 24 * 60, 3, 1, 1.0)
    sample = {"project_key": project.key, "stats_reset": None, "statements": []}
    cluster.query(f"SELECT app.control_record_insights('{json.dumps(sample)}'::jsonb)")
    kept = cluster.query(
        f"SELECT queryid FROM app.control_insight_samples WHERE project_key = '{project.key}' "
        "ORDER BY queryid"
    )
    assert kept == ["2"], kept
    assert cluster.query(
        f"SELECT count(*) FROM app.control_insight_samples WHERE project_key = '{other.key}'"
    ) == ["1"]
