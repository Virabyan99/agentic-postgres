"""Long operations made visible (CTL-STEPS-001, CTL-NOTIFY-002; ADR 0296, ADR 0297).

Control set 0011 records when each step of an operation began, in
`app.control_operation_steps` -- written only by `control_advance_operation`,
the reconciler's call, granted to nobody, and readable only through the two
operation readers, which serve it as `steps` beside a `subject` that names what
the operation acts on and never any other argument. `GET /v1/operations` takes
`status=open`; every read serves `expected` from `operation_steps`. A request
for a long operation writes an `operation_started` notification, and every
notification an operation writes names the operation.

Every property is read from a real control cluster through the role the control
mode connects as, or through the route.
"""

# ruff: noqa: S608 -- every interpolated value is a uuid or a key this module made.

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Iterator
from typing import Any

import control_cluster as cc
import pytest

from agentic_postgres import REPO_ROOT, operation_steps, operations

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

TEMPLATES = REPO_ROOT / "projects" / "control" / "migrations" / "templates"
SCHEMA = REPO_ROOT / "schemas" / "operation-arguments.schema.json"
HANDOFF = "ab" * 32
#: ADR 0296 decision 2: the argument members a subject may carry, per type.
SUBJECT = {
    "project.create": {"name", "profile"},
    "project.resize": {"profile"},
    "branch.create": {"branch"},
    "restore.create": {"branch"},
    "branch.reset": {"branch"},
    "branch.delete": {"branch"},
}
#: The four types whose request says it started (ADR 0297 decision 5).
STARTED = {"project.create", "branch.create", "restore.create", "branch.reset"}


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    try:
        with cc.control_cluster() as started:
            with cc.control_app(started, tmp_path_factory.mktemp("control-steps")) as driver:
                yield driver
    except RuntimeError as error:
        pytest.skip(str(error))


@pytest.fixture(scope="module")
def cluster(drive: Any) -> cc.ControlCluster:
    return drive.cluster


@pytest.fixture
def accepting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(operations, "ACCEPTED_TYPES", operations.EXECUTED_TYPES)


def _org(cluster: cc.ControlCluster) -> dict[str, str]:
    """An owner, their organisation and one adopted project, made directly."""
    tag = uuid.uuid4().hex[:8]
    user = str(uuid.uuid4())
    cluster.query(
        "INSERT INTO app.control_accounts (user_id, username, display_name) "
        f"VALUES ('{user}', 's-{tag}', 'S')"
    )
    org = cluster.query(
        f"INSERT INTO app.control_organizations (name, created_by) VALUES ('s {tag}', "
        f"'{user}') RETURNING id"
    )[0]
    cluster.query(
        "INSERT INTO app.control_memberships (organization_id, user_id, role) "
        f"VALUES ('{org}', '{user}', 'owner')"
    )
    key = f"s{tag}-prod"
    cluster.query(
        f"SELECT app.control_adopt_project('{key}', '{org}', 's{tag}', 'prod', '{key}.test', "
        "'1.24.0', 'abc')"
    )
    return {"user": user, "org": org, "key": key}


def _operation(
    cluster: cc.ControlCluster,
    org: dict[str, str],
    kind: str,
    status: str,
    arguments: dict[str, Any] | None = None,
    key: str | None = "project",
) -> str:
    project = "NULL" if key is None else f"'{org['key'] if key == 'project' else key}'"
    started = "now()" if status != "pending" else "NULL"
    return cluster.query(
        "INSERT INTO app.control_operations (organization_id, project_key, type, status, "
        "requested_by, arguments, started_at) VALUES "
        f"('{org['org']}', {project}, '{kind}', '{status}', '{org['user']}', "
        f"'{json.dumps(arguments or {})}', {started}) RETURNING id"
    )[0]


def _read(cluster: cc.ControlCluster, user: str, op: str) -> dict[str, Any] | None:
    rows = cluster.as_service(
        f"SELECT row_to_json(r) FROM app.control_get_operation('{user}', '{op}') r"
    )
    return json.loads(rows[0]) if rows else None


def test_each_step_is_logged_once_in_order(cluster: cc.ControlCluster) -> None:
    """The reconciler's advances, each its own transaction: three steps, in the
    order they began, a repeated step keeping its FIRST time; the member's reader
    serves them. Goes red if: the advance stops logging, logs a repeat again, or a
    reader drops `steps`."""
    org = _org(cluster)
    op = _operation(cluster, org, "project.create", "running", key=None)
    for step, progress in (("allocate", 10), ("admit", 10), ("admit", 10), ("deploy-1", 30)):
        cluster.query(f"SELECT app.control_advance_operation('{op}', '{step}', {progress})")
        time.sleep(0.05)
    row = _read(cluster, org["user"], op)
    assert row is not None
    assert [s["step"] for s in row["steps"]] == ["allocate", "admit", "deploy-1"], row["steps"]
    starts = [s["started_at"] for s in row["steps"]]
    assert starts == sorted(starts) and len(set(starts)) == 3, starts
    (listed,) = [
        json.loads(r) for r in cluster.as_service(
            f"SELECT row_to_json(r) FROM app.control_list_operations('{org['user']}', "
            f"'{org['org']}') r WHERE r.id = '{op}'"
        )
    ]  # fmt: skip
    assert listed["steps"] == row["steps"]
    # Control: an operation never advanced serves an empty list, not null.
    pending = _operation(cluster, org, "project.sleep", "pending")
    assert (_read(cluster, org["user"], pending) or {})["steps"] == []


def test_the_step_log_is_granted_to_nobody(cluster: cc.ControlCluster) -> None:
    """No request role reads the table; the identity service's role is refused;
    a non-member's reader sees no row. Control: the superuser reads the rows,
    and the member's reader reads its operation."""
    org, stranger = _org(cluster), _org(cluster)
    op = _operation(cluster, org, "project.wake", "running")
    cluster.query(f"SELECT app.control_advance_operation('{op}', 'start', 10)")
    denied = cluster.refused("SELECT count(*) FROM app.control_operation_steps")
    assert "permission denied" in denied, denied
    assert cluster.query(
        f"SELECT count(*) FROM app.control_operation_steps WHERE operation_id = '{op}'"
    ) == ["1"]
    assert _read(cluster, stranger["user"], op) is None
    assert _read(cluster, org["user"], op) is not None
    forced = cluster.query(
        "SELECT relforcerowsecurity FROM pg_class "
        "WHERE oid = 'app.control_operation_steps'::regclass"
    )
    assert forced == ["t"]


def test_a_finished_operation_gains_no_step(cluster: cc.ControlCluster) -> None:
    org = _org(cluster)
    op = _operation(cluster, org, "project.export", "running")
    cluster.query(f"SELECT app.control_advance_operation('{op}', 'dump', 10)")
    cluster.query(f"SELECT app.control_finish_operation('{op}', 'succeeded', NULL, NULL)")
    late = cluster.run(f"SELECT app.control_advance_operation('{op}', 'upload', 60)")
    assert late.returncode != 0 and "not_running" in late.stderr
    assert cluster.query(
        f"SELECT count(*) FROM app.control_operation_steps WHERE operation_id = '{op}'"
    ) == ["1"]


def _schema_members() -> dict[str, set[str]]:
    """Every argument member the operation schema allows, per type."""
    document = json.loads(SCHEMA.read_text(encoding="utf-8"))
    members: dict[str, set[str]] = {}
    for branch in document["oneOf"]:
        kind = branch.get("properties", {}).get("type", {}).get("const")
        arguments = branch.get("properties", {}).get("arguments", {})
        members[kind] = set(arguments.get("properties", {}))
    return members


def test_the_subject_names_only_what_the_operation_acts_on(cluster: cc.ControlCluster) -> None:
    """ADR 0296 decision 2, derived from the schema: each type's operation is
    written with EVERY argument member it allows, each a distinct value; the
    reader serves exactly the subject's members, and no other member's name or
    value appears anywhere in the row. Goes red if: a reader serves
    `arguments`, or a subject grows a member this module does not name."""
    members = _schema_members()
    assert set(members) == set(operations.EXECUTED_TYPES)
    for kind, allowed in members.items():
        org = _org(cluster)  # one open operation per project (D2166): one project each
        values = {m: f"v{uuid.uuid4().hex[:10]}" for m in allowed}
        op = _operation(cluster, org, kind, "pending", values,
                        key=None if kind == "project.create" else "project")  # fmt: skip
        row = _read(cluster, org["user"], op)
        assert row is not None, kind
        expected = {m: values[m] for m in SUBJECT.get(kind, set())}
        assert row["subject"] == expected, (kind, row["subject"])
        whole = json.dumps(row)
        for member, value in values.items():
            if member not in expected:
                assert value not in whole and f'"{member}"' not in whole, (kind, member)
        assert "arguments" not in row


def test_the_route_serves_steps_subject_and_expected(drive: Any, accepting: None) -> None:
    """Through `/v1`: a creation requested by the route reads back its subject
    (the name and profile it was asked with -- never the digest or the
    administrator), its steps, and `expected` equal to `operation_steps`."""
    people = _people(drive, "route", project=False)
    _ready_slot(drive)
    body = {"organization": people["org"], "name": "Notes app", "profile": "small",
            "admin_username": "ana.admin", "handoff_sha256": HANDOFF}  # fmt: skip
    asked = drive.call("POST", "/v1/projects", token=people["member"], body=body)
    assert asked.status_code == 202, asked.text
    op = asked.json()["operation"]["id"]
    drive.cluster.query(
        "UPDATE app.control_operations SET status = 'running', started_at = now() "
        f"WHERE id = '{op}'"
    )
    drive.cluster.query(f"SELECT app.control_advance_operation('{op}', 'allocate', 10)")
    read = drive.call("GET", f"/v1/operations/{op}", token=people["viewer"])
    assert read.status_code == 200, read.text
    document = read.json()
    assert document["subject"] == {"name": "Notes app", "profile": "small"}
    assert [s["step"] for s in document["steps"]] == ["allocate"]
    assert document["expected"] == operation_steps.expected("project.create")
    assert HANDOFF not in read.text and "ana.admin" not in read.text
    notices = drive.call("GET", f"/v1/organizations/{people['org']}/notifications?limit=5",
                         token=people["viewer"]).json()["notifications"]  # fmt: skip
    assert [(n["kind"], n["operation_id"], n["operation_type"]) for n in notices] == [
        ("operation_started", op, "project.create")
    ], notices
    assert all(HANDOFF not in n["text"] for n in notices)


def test_status_open_lists_only_what_is_in_flight(drive: Any) -> None:
    """`?status=open`: pending and running, never a finished one; any other value
    is `invalid_request`; without it the list is unchanged."""
    people = _people(drive, "open")
    org = {"org": people["org"], "user": people["member_id"], "key": people["project"]}
    pending = _operation(drive.cluster, org, "project.sleep", "pending")
    done = _operation(drive.cluster, org, "project.create", "running", key=None)
    drive.cluster.query(f"SELECT app.control_finish_operation('{done}', 'succeeded', NULL, NULL)")
    path = f"/v1/operations?organization={people['org']}"
    every = {o["id"] for o in drive.call("GET", path, token=people["viewer"]).json()["operations"]}
    opened = drive.call("GET", path + "&status=open", token=people["viewer"])
    assert opened.status_code == 200, opened.text
    assert {o["id"] for o in opened.json()["operations"]} == {pending}
    assert {pending, done} <= every
    wrong = drive.call("GET", path + "&status=finished", token=people["viewer"])
    assert (wrong.status_code, wrong.json()["error"]) == (422, "invalid_request")


def test_a_long_request_says_it_started(cluster: cc.ControlCluster) -> None:
    """ADR 0297 decision 5: `control_request_operation` writes ONE
    `operation_started` notice for a creation, a branch, a restore and a reset,
    naming the operation; no other type writes one at request. Goes red if: the
    notice goes missing, or every request writes one."""
    org = _org(cluster)
    branch = {"branch": "dev", "app_verifier": "x", "admin_verifier": "x"}
    asked = {}
    for kind, project, arguments in (
        ("branch.create", org["key"], branch),
        ("project.sleep", org["key"], {}),
    ):
        (answer,) = cluster.as_service(
            f"SELECT operation_id FROM app.control_request_operation('{org['user']}', "
            f"'{org['org']}', '{project}', '{kind}', '{json.dumps(arguments)}'::jsonb)"
        )
        asked[kind] = answer
        cluster.query(
            f"UPDATE app.control_operations SET status = 'cancelled' WHERE id = '{answer}'"
        )
    rows = cluster.query(
        "SELECT kind || '|' || coalesce(operation_id::text, '-') || '|' "
        "|| coalesce(operation_type, '-') "
        f"FROM app.control_notifications WHERE organization_id = '{org['org']}' ORDER BY created_at"
    )
    assert rows == [f"operation_started|{asked['branch.create']}|branch.create"], rows


def test_a_finished_operation_names_its_operation(cluster: cc.ControlCluster) -> None:
    org = _org(cluster)
    op = _operation(cluster, org, "project.sleep", "running")
    cluster.query(f"SELECT app.control_finish_operation('{op}', 'succeeded', NULL, NULL)")
    (row,) = cluster.as_service(
        "SELECT kind || '|' || operation_id || '|' || operation_type FROM "
        f"app.control_list_notifications('{org['user']}', '{org['org']}', 10)"
    )
    assert row == f"operation_succeeded|{op}|project.sleep", row


def test_the_notifications_route_names_the_operation(drive: Any) -> None:
    people = _people(drive, "notified")
    org = {"org": people["org"], "user": people["member_id"], "key": people["project"]}
    op = _operation(drive.cluster, org, "project.wake", "running")
    drive.cluster.query(f"SELECT app.control_finish_operation('{op}', 'succeeded', NULL, NULL)")
    listed = drive.call("GET", f"/v1/organizations/{people['org']}/notifications?limit=5",
                        token=people["viewer"])  # fmt: skip
    assert listed.status_code == 200, listed.text
    (notice,) = listed.json()["notifications"]
    assert (notice["kind"], notice["operation_id"], notice["operation_type"]) == (
        "operation_succeeded", op, "project.wake",
    )  # fmt: skip


def _function(path: Any, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    found = re.findall(
        rf"(CREATE OR REPLACE FUNCTION app\.{name}\(.*?\n\$\$;)", text, flags=re.DOTALL
    )
    assert len(found) == 1, (path.name, name, len(found))
    return found[0]


def test_0011s_finish_is_0008s_but_for_the_operation() -> None:
    """The finish gained two columns and two values in its one insert, nothing
    else (test_notifications holds 0008's against 0004's)."""
    before = _function(TEMPLATES / "0008-control-plans-usage.sql", "control_finish_operation")
    after = _function(TEMPLATES / "0011-control-operation-steps.sql", "control_finish_operation")
    widened = "(organization_id, project_key, kind, text, operation_id, operation_type)"
    assert after.count(widened) == 1 and after.count("    p_id, v_type\n  );") == 1
    restored = after.replace(widened, "(organization_id, project_key, kind, text)").replace(
        "         END,\n    p_id, v_type\n  );", "         END\n  );"
    )
    assert restored == before


def _people(drive: Any, label: str, *, project: bool = True) -> dict[str, Any]:
    tag = f"{label}-{uuid.uuid4().hex[:6]}"
    owner = drive.account(f"{tag}-owner")
    org = drive.organization(owner, tag)
    drive.token(f"{tag}-owner", drive.enable_factor(owner))
    people: dict[str, Any] = {"org": org}
    for role in ("member", "viewer"):
        user = drive.account(f"{tag}-{role}")
        drive.member(org, user, role)
        people[f"{role}_id"] = user
        people[role] = drive.token(f"{tag}-{role}")
    people["project"] = None
    if project:
        key = f"q{uuid.uuid4().hex[:8]}-prod"
        drive.cluster.query(
            f"SELECT app.control_adopt_project('{key}', '{org}', '{key[:9]}', 'prod', "
            f"'{key}.test', '1.24.0', 'abc')"
        )
        people["project"] = key
    return people


def _ready_slot(drive: Any) -> None:
    reading = [{"key": "slot5-prod", "state": "ready", "region_id": "eu-hel-1"}]
    drive.cluster.query("DELETE FROM app.control_slots")
    drive.cluster.query(f"SELECT app.control_record_slots('{json.dumps(reading)}'::jsonb)")
