"""Usage samples and the usage document (Session 41, ADR 0275, D2523, D2524).

The reconciler writes one sample per project every 300 s through
`app.control_record_usage`, granted to nobody; a figure it could not read is
NULL and named in `unread`. A member reads the document `control_usage_document`
computes -- once, in SQL -- through `control_project_usage` /
`control_org_usage`: samples expected and present, each gauge's newest READ
value, the request counter's increases with a decrease read as a reset (D553),
the sums, and active and sleeping seconds from the operation history (never
sampled). A window with no sample says so; it is never zeros.
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


@pytest.fixture(scope="module")
def cluster() -> Iterator[cc.ControlCluster]:
    try:
        with cc.control_cluster() as started:
            yield started
    except RuntimeError as error:
        pytest.skip(str(error))


class Project:
    def __init__(self, cluster: cc.ControlCluster, *, adopted_hours_ago: int = 48) -> None:
        self.cluster = cluster
        tag = uuid.uuid4().hex[:8]
        self.user = str(uuid.uuid4())
        cluster.query(
            "INSERT INTO app.control_accounts (user_id, username, display_name) "
            f"VALUES ('{self.user}', 'u-{tag}', 'U')"
        )
        self.org = cluster.query(
            f"INSERT INTO app.control_organizations (name, created_by) VALUES ('u {tag}', "
            f"'{self.user}') RETURNING id"
        )[0]
        cluster.query(
            "INSERT INTO app.control_memberships (organization_id, user_id, role) "
            f"VALUES ('{self.org}', '{self.user}', 'viewer')"
        )
        self.key = f"u{tag}-prod"
        cluster.query(
            f"SELECT app.control_adopt_project('{self.key}', '{self.org}', 'u{tag}', 'prod', "
            f"'{self.key}.test', '1.19.0', 'abc')"
        )
        cluster.query(
            "UPDATE app.control_projects SET adopted_at = now() - "
            f"interval '{adopted_hours_ago} hours' WHERE key = '{self.key}'"
        )

    def sample(self, minutes_ago: int, **figures: Any) -> None:
        columns = ", ".join(["project_key", "observed_at", "state", *figures])
        values = [f"'{self.key}'", f"now() - interval '{minutes_ago} minutes'", "'active'"]
        for value in figures.values():
            if value is None:
                values.append("NULL")
            elif isinstance(value, list):
                values.append("ARRAY[" + ",".join(f"'{v}'" for v in value) + "]::text[]")
            else:
                values.append(str(value))
        self.cluster.query(
            f"INSERT INTO app.control_usage_samples ({columns}) VALUES ({', '.join(values)})"
        )

    def event(self, kind: str, hours_ago: float) -> None:
        self.cluster.query(
            "INSERT INTO app.control_operations (organization_id, project_key, type, status, "
            "requested_by, arguments, started_at, finished_at, claimed_by, attempt, progress) "
            f"VALUES ('{self.org}', '{self.key}', '{kind}', 'succeeded', '{self.user}', '{{}}', "
            f"now() - interval '{hours_ago} hours' - interval '1 minute', "
            f"now() - interval '{hours_ago} hours', 'proof', 1, 100)"
        )

    def usage(self, hours: int = 24) -> dict[str, Any]:
        (text,) = self.cluster.as_service(
            f"SELECT app.control_project_usage('{self.user}', '{self.key}', {hours})"
        )
        return json.loads(text)


def test_no_role_but_the_reconciler_writes_a_sample(cluster: cc.ControlCluster) -> None:
    """THR-USE-TAMPER (D2533): the identity service's role can neither execute
    the writer nor touch the table; the writer, as the reconciler reaches it,
    records one sample with its unread names and refuses a member it does not
    know."""
    project = Project(cluster)
    (held,) = cluster.query(
        f"SELECT has_function_privilege('{cluster.auth_role}', 'app.control_record_usage(jsonb)', "
        "'EXECUTE')"
    )
    assert held == "f"
    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        (table,) = cluster.query(
            f"SELECT has_table_privilege('{cluster.auth_role}', 'app.control_usage_samples', "
            f"'{privilege}')"
        )
        assert table == "f", privilege
    sample = {
        "project_key": project.key, "state": "active", "database_bytes": 10548927,
        "repository_bytes": None, "unread": ["repository_bytes"],
        "reason": "the backup repository could not be read",
    }  # fmt: skip
    payload = json.dumps([sample]).replace("'", "''")
    assert cluster.query(f"SELECT app.control_record_usage('{payload}'::jsonb)") == ["1"]
    (row,) = cluster.query(
        "SELECT database_bytes || '|' || coalesce(repository_bytes::text, 'NULL') || '|' || "
        "array_to_string(unread, ',') FROM app.control_usage_samples "
        f"WHERE project_key = '{project.key}'"
    )
    assert row == "10548927|NULL|repository_bytes", row
    bad = json.dumps([{**sample, "requests": 1}]).replace("'", "''")
    assert (
        "AP422: invalid_samples"
        in cluster.run(f"SELECT app.control_record_usage('{bad}'::jsonb)").stderr
    )


def test_a_counter_reset_is_read_not_subtracted(cluster: cc.ControlCluster) -> None:
    """D553: 100 -> 150 -> 30 -> 70 is +50, a reset counted from zero (+30), +40:
    120 with one reset -- never 70 - 100. A sample that could not read the
    counter is skipped, not read as zero."""
    project = Project(cluster)
    for minutes, value in ((20, 100), (15, 150), (12, None), (10, 30), (5, 70)):
        project.sample(minutes, requests_counter=value)
    document = project.usage()
    assert document["requests"] == {"increase": 120, "resets": 1}, document["requests"]
    assert document["samples"]["present"] == 5


def test_each_gauge_is_its_newest_read_value(cluster: cc.ControlCluster) -> None:
    """A gauge's `latest` is the newest sample that READ it, with its instant; the
    sample after it that could not read it is counted in `unread_samples`."""
    project = Project(cluster)
    project.sample(10, database_bytes=1000)
    project.sample(5, database_bytes=2000)
    project.sample(1, database_bytes=None, unread=["database_bytes"])
    figure = project.usage()["figures"]["database_bytes"]
    assert (figure["latest"], figure["max"], figure["unread_samples"]) == (2000, 2000, 1), figure
    assert figure["latest_at"] is not None


def test_seconds_come_from_the_history(cluster: cc.ControlCluster) -> None:
    """Active and sleeping seconds over a 6-hour window from the operation
    history: awake from -6 h, asleep from -4 h, awake from -1 h -- 3 h each,
    whatever the samples say (there are none)."""
    project = Project(cluster, adopted_hours_ago=10)
    project.event("project.sleep", 4)
    project.event("project.wake", 1)
    document = project.usage(hours=6)
    assert abs(document["active_seconds"] - 3 * 3600) <= 5, document
    assert abs(document["sleeping_seconds"] - 3 * 3600) <= 5, document


def test_an_empty_window_is_not_zero(cluster: cc.ControlCluster) -> None:
    """No sample in the window: `present` 0 against what was expected, and every
    figure null -- the document cannot say a project used nothing."""
    project = Project(cluster)
    document = project.usage(hours=2)
    assert document["samples"] == {"expected": 24, "present": 0}, document["samples"]
    assert document["requests"] is None
    assert document["agent_calls"] is None and document["workflow_runs"] is None
    assert all(f["latest"] is None and f["max"] is None for f in document["figures"].values())


def test_a_foreign_and_a_missing_project_answer_alike(cluster: cc.ControlCluster) -> None:
    """THR-CTL-ENUMERATION's rule: another organisation's project and a project
    that does not exist read the one `not_found`; a window outside 1..720 hours
    is refused; the organisation's document holds its own projects only."""
    mine, theirs = Project(cluster), Project(cluster)
    foreign = cluster.refused(
        f"SELECT app.control_project_usage('{mine.user}', '{theirs.key}', 24)"
    )
    missing = cluster.refused(f"SELECT app.control_project_usage('{mine.user}', 'nope-prod', 24)")
    assert "AP404: not_found" in foreign and "AP404: not_found" in missing, (foreign, missing)
    for hours in (0, 721):
        assert "AP422" in cluster.refused(
            f"SELECT app.control_project_usage('{mine.user}', '{mine.key}', {hours})"
        )
    (text,) = cluster.as_service(f"SELECT app.control_org_usage('{mine.user}', '{mine.org}', 24)")
    assert [p["project_key"] for p in json.loads(text)["projects"]] == [mine.key]
    assert "AP404" in cluster.refused(
        f"SELECT app.control_org_usage('{mine.user}', '{theirs.org}', 24)"
    )
