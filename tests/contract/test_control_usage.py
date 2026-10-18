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

from app import signals

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    """One control cluster and the control mode over it (Run 5's routes)."""
    try:
        with cc.control_cluster() as started:
            with cc.control_app(started, tmp_path_factory.mktemp("control-usage")) as driver:
                yield driver
    except RuntimeError as error:
        pytest.skip(str(error))


@pytest.fixture(scope="module")
def cluster(drive: Any) -> cc.ControlCluster:
    return drive.cluster


def _people(drive: Any, label: str) -> dict[str, Any]:
    """A route caller's organisation: an owner, a member, a viewer, their tokens,
    and one adopted project."""
    tag = f"{label}-{uuid.uuid4().hex[:6]}"
    people: dict[str, Any] = {"tokens": {}, "users": {}}
    owner = drive.account(f"{tag}-owner")
    people["id"] = drive.organization(owner, tag)
    people["tokens"]["owner"] = drive.token(f"{tag}-owner", drive.enable_factor(owner))
    for role in ("member", "viewer"):
        user = drive.account(f"{tag}-{role}")
        drive.member(people["id"], user, role)
        people["users"][role] = user
        people["tokens"][role] = drive.token(f"{tag}-{role}")
    key = f"r{uuid.uuid4().hex[:8]}-prod"
    drive.cluster.query(
        f"SELECT app.control_adopt_project('{key}', '{people['id']}', '{key[:9]}', 'prod', "
        f"'{key}.test', '1.19.0', 'abc')"
    )
    people["project"] = key
    return people


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


# ---------------------------------------------------------------------------
# Session 42 (ADR 0278, D2570): DB time
# ---------------------------------------------------------------------------


def test_db_time_is_a_sum_of_increases(cluster: cc.ControlCluster) -> None:
    """D553, the request counter's reading applied to DB time: 100 -> 150 ms,
    then `statements_reset` MOVED (30 ms), then 70 ms, then a DECREASE (20 ms)
    -- +50, reset +30, +40, reset +20: 140 ms with two resets. A sample that
    could not read it is skipped, never read as zero."""
    project = Project(cluster)
    first, second = "'2026-10-18 00:00:00+00'", "'2026-10-18 01:00:00+00'"
    for minutes, ms, reset in ((25, 100, first), (20, 150, first), (15, None, first),
                               (10, 30, second), (5, 70, second), (2, 20, second)):  # fmt: skip
        project.sample(minutes, db_time_ms=ms, statements_reset=reset)
    assert project.usage()["db_time"] == {"increase_ms": 140, "resets": 2}, project.usage()


def test_db_time_unread_is_named(cluster: cc.ControlCluster) -> None:
    """The writer accepts `db_time_ms` NULL named in `unread` (the extension not
    loaded, or not readable) and the CHECK admits the name; a window where no
    sample read it says null -- not zero -- in the document."""
    project = Project(cluster)
    sample = {
        "project_key": project.key, "state": "active", "db_time_ms": None,
        "statements_reset": None, "unread": ["db_time_ms"],
        "reason": "db_time_ms: the cluster did not answer (is pg_stat_statements loaded?)",
    }  # fmt: skip
    payload = json.dumps([sample]).replace("'", "''")
    assert cluster.query(f"SELECT app.control_record_usage('{payload}'::jsonb)") == ["1"]
    assert project.usage()["db_time"] is None
    bogus = json.dumps([{**sample, "unread": ["db_time"]}]).replace("'", "''")
    assert (
        "control_usage_samples_unread_check"
        in cluster.run(f"SELECT app.control_record_usage('{bogus}'::jsonb)").stderr
    )


def _function_body(template: str, name: str) -> str:
    text = (cc.REPO_ROOT / "projects/control/migrations/templates" / template).read_text("utf-8")
    start = text.index(f"FUNCTION app.{name}(")
    body_start = text.index("AS $$", start)
    return text[body_start : text.index("$$;", body_start + 5)]


def test_the_usage_writer_is_0008s_plus_two_keys() -> None:
    """0009 re-creates `control_record_usage`; its body is 0008's with ONLY
    `db_time_ms` and `statements_reset` added -- the whitelist's two names,
    the insert's two columns, their two casts. Removing exactly those lines
    gives 0008's body back, byte for byte."""
    before = _function_body("0008-control-plans-usage.sql", "control_record_usage")
    after = _function_body("0009-control-insights.sql", "control_record_usage")
    added = [line for line in after.splitlines() if line not in before.splitlines()]
    assert added == [
        "            'workflow_runs', 'last_customer_activity', 'unread', 'reason',",
        "            'db_time_ms', 'statements_reset'",
        "    last_customer_activity, unread, reason,",
        "    db_time_ms, statements_reset",
        "         s ->> 'reason',",
        "         (s ->> 'db_time_ms')::double precision, (s ->> 'statements_reset')::timestamptz",
    ], added
    restored = (
        after.replace(added[0] + "\n" + added[1], added[0].rstrip(","))
        .replace(added[2] + "\n" + added[3], added[2].rstrip(","))
        .replace(added[4] + "\n" + added[5], added[4].rstrip(","))
    )
    assert restored == before


# ---------------------------------------------------------------------------
# The routes (Run 5)
# ---------------------------------------------------------------------------


def test_the_usage_route_says_when_it_could_not_determine(drive: Any) -> None:
    """`GET /v1/projects/{key}/usage`: a window with no sample is
    `could_not_determine` with its reason -- never zeros; with a sample it is
    `read`, and each shown limit names the figure it is read against and that it
    is not enforced."""
    people = _people(drive, "usage")
    path = f"/v1/projects/{people['project']}/usage"
    empty = drive.call("GET", path + "?hours=2", token=people["tokens"]["viewer"])
    assert empty.status_code == 200, empty.text
    assert (empty.json()["status"], empty.json()["reason"]) == (
        "could_not_determine", "no usage sample was recorded in this window",
    )  # fmt: skip
    drive.cluster.query(
        "INSERT INTO app.control_usage_samples (project_key, observed_at, state, database_bytes) "
        f"VALUES ('{people['project']}', now() - interval '5 minutes', 'active', 4242)"
    )
    read = drive.call("GET", path, token=people["tokens"]["viewer"]).json()
    assert read["status"] == "read" and read["figures"]["database_bytes"]["latest"] == 4242
    shown = {e["name"]: e for e in read["entitlements"]}
    assert shown["storage_gb"] == {"name": "storage_gb", "value": 5, "enforced": False,
                                   "against": "database_bytes"}  # fmt: skip
    assert shown["agent_calls_per_day"]["enforced"] is False
    organization = drive.call(
        "GET", f"/v1/organizations/{people['id']}/usage", token=people["tokens"]["viewer"]
    )
    assert organization.status_code == 200, organization.text
    assert [p["project_key"] for p in organization.json()["projects"]] == [people["project"]]


def test_the_usage_routes_answer_a_foreign_and_a_missing_project_alike(drive: Any) -> None:
    """Through the route: another organisation's project and a missing one are
    one `not_found`; a window outside 1..720 hours, a non-number and an unknown
    parameter are each refused before anything is read."""
    mine, theirs = _people(drive, "mine"), _people(drive, "theirs")
    token = mine["tokens"]["viewer"]
    foreign = drive.call("GET", f"/v1/projects/{theirs['project']}/usage", token=token)
    missing = drive.call("GET", "/v1/projects/nope-prod/usage", token=token)
    assert (foreign.status_code, foreign.json()) == (missing.status_code, missing.json())
    assert foreign.status_code == 404 and foreign.json()["error"] == "not_found"
    for query in ("hours=0", "hours=721", "hours=ten", "hours=2&days=1"):
        refused = drive.call("GET", f"/v1/projects/{mine['project']}/usage?{query}", token=token)
        assert refused.status_code == 422, (query, refused.text)
    assert drive.call("GET", f"/v1/organizations/{theirs['id']}/usage",
                      token=token).status_code == 404  # fmt: skip


# ---------------------------------------------------------------------------
# The insights and monitoring routes (Session 42, Run 7)
# ---------------------------------------------------------------------------


def test_the_insights_and_monitoring_routes_answer_a_viewer_and_a_read_key(drive: Any) -> None:
    """ADR 0278/0279 through the routes: a viewer and a key holding only
    `projects:read` read both, a key holding only `organizations:read` is refused;
    an empty window's insights are `could_not_determine` with `statements` null;
    monitoring lists every signal of `signals.SIGNALS` in order, each naming its
    source, a reading the control database did not make `unread` -- never
    dropped. A window outside 1..168, a limit outside 1..50 and an unknown
    parameter are refused before anything is read."""
    people = _people(drive, "insight")
    project = people["project"]
    keys = {}
    for scope in ("projects:read", "organizations:read"):
        minted = drive.call(
            "POST", f"/v1/organizations/{people['id']}/keys", token=people["tokens"]["member"],
            body={"name": scope.split(":")[0], "scopes": [scope]},
        )  # fmt: skip
        assert minted.status_code == 201, minted.text
        keys[scope] = minted.json()["key"]
    for token in (people["tokens"]["viewer"], keys["projects:read"]):
        insights = drive.call("GET", f"/v1/projects/{project}/insights?hours=2", token=token)
        assert insights.status_code == 200, insights.text
        assert (insights.json()["status"], insights.json()["statements"]) == (
            "could_not_determine", None,
        )  # fmt: skip
        monitoring = drive.call("GET", f"/v1/projects/{project}/monitoring", token=token)
        assert monitoring.status_code == 200, monitoring.text
        shown = monitoring.json()["signals"]
        assert [s["name"] for s in shown] == [s.name for s in signals.SIGNALS]
        assert [s["source"] for s in shown] == [s.source for s in signals.SIGNALS]
        assert all(s["value"] is not None or s.get("unread") for s in shown), shown
    for path in ("insights", "monitoring"):
        refused = drive.call(
            "GET", f"/v1/projects/{project}/{path}", token=keys["organizations:read"]
        )
        assert refused.status_code == 403, (path, refused.text)
    for query in ("hours=0", "hours=169", "limit=0", "limit=51", "hours=2&days=1"):
        refused = drive.call(
            "GET", f"/v1/projects/{project}/insights?{query}", token=people["tokens"]["viewer"]
        )
        assert refused.status_code == 422, (query, refused.text)
    unknown = drive.call(
        "GET", f"/v1/projects/{project}/monitoring?hours=2", token=people["tokens"]["viewer"]
    )
    assert unknown.status_code == 422, unknown.text
