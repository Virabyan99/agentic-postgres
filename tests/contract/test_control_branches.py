"""A project's branches, restores and backups through `/v1`, against a real
control cluster (Session 40; ADR 0271, ADR 0272, ADR 0273; D2430, D2433, D2438,
D2451, D2468).

The routes answer `not_available` in the product until the branch rows are
`trial` (Run 8); these proofs accept the executed types for their own duration
(`accepting`), as `test_control_projects` does, and one proof reads the
refusal without it. The reconciler's half -- recording a branch, a backups
reading, an expiry -- is played by the superuser calling the set's invoker
functions, which are granted to nobody.
"""

# ruff: noqa: S608 -- every interpolated value is a uuid, a key or a name this
# module wrote, run against a throwaway cluster.

from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import control_cluster as cc
import pytest

from app import operations

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

VERIFIER = (
    "SCRAM-SHA-256$4096:c2FsdHNhbHRzYWx0c2FsdA==$"
    "U3RvcmVkS2V5U3RvcmVkS2V5U3RvcmVkS2V5U3RvcmU=:"
    "U2VydmVyS2V5U2VydmVyS2V5U2VydmVyS2V5U2VydmU="
)
BRANCH = {"branch": "dev", "app_verifier": VERIFIER, "admin_verifier": VERIFIER}


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Any:
    try:
        with cc.control_cluster() as cluster:
            with cc.control_app(cluster, tmp_path_factory.mktemp("control-branches")) as driver:
                yield driver
    except RuntimeError as exc:
        pytest.skip(str(exc))


@pytest.fixture
def accepting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every executed type accepted, for this proof only."""
    monkeypatch.setattr(operations, "ACCEPTED_TYPES", operations.EXECUTED_TYPES)


def _org(drive: Any, label: str) -> dict[str, Any]:
    tag = f"{label}-{uuid.uuid4().hex[:6]}"
    people: dict[str, Any] = {"tokens": {}, "users": {}}
    owner = drive.account(f"{tag}-owner")
    people["users"]["owner"] = owner
    people["id"] = drive.organization(owner, tag)
    people["tokens"]["owner"] = drive.token(f"{tag}-owner", drive.enable_factor(owner))
    for role in ("member", "viewer"):
        user = drive.account(f"{tag}-{role}")
        drive.member(people["id"], user, role)
        people["users"][role] = user
        people["tokens"][role] = drive.token(f"{tag}-{role}")
    key = f"b{uuid.uuid4().hex[:8]}-prod"
    drive.cluster.query(
        f"SELECT app.control_adopt_project('{key}', '{people['id']}', '{key[:9]}', 'prod', "
        f"'{key}.test', '1.18.0', 'abc')"
    )
    people["project"] = key
    return people


def _record_branch(drive: Any, key: str, name: str = "dev", **extra: Any) -> None:
    """The reconciler's reading of the host, for this project's one branch only."""
    entry = {"project_key": key, "name": name, "state": "ready", **extra}
    drive.cluster.query(f"SELECT app.control_record_branches('{json.dumps([entry])}'::jsonb)")


def _rows(drive: Any, key: str) -> int:
    return int(
        drive.cluster.query(
            f"SELECT count(*) FROM app.control_operations WHERE project_key = '{key}'"
        )[0]
    )


def _finish(drive: Any, key: str) -> None:
    drive.cluster.query(
        "UPDATE app.control_operations SET status = 'succeeded', finished_at = now() "
        f"WHERE project_key = '{key}' AND status IN ('pending', 'running')"
    )


def _key(drive: Any, org: dict[str, Any], scopes: list[str]) -> str:
    minted = drive.call(
        "POST", f"/v1/organizations/{org['id']}/keys", token=org["tokens"]["member"],
        body={"name": "automation", "scopes": scopes},
    )  # fmt: skip
    assert minted.status_code == 201, minted.text
    return minted.json()["key"]


def test_a_second_branch_is_refused_before_a_row(drive: Any, accepting: None) -> None:
    """D2430: the first creation records a row; a second, while it is pending, is
    `409 branch_limit_reached` and writes nothing -- and so is one after the
    branch is recorded live, a restore included. The control set refuses the
    same on its own: called directly, bypassing the route, it raises `AP409:
    branch_limit_reached`. Neither reader produces `capacity_exhausted`.

    Goes red if: the limit counts only rows (not recorded branches) or only
    branches (not creations in flight), or the refusal writes a row."""
    org = _org(drive, "limit")
    key, member = org["project"], org["tokens"]["member"]
    first = drive.call("POST", f"/v1/projects/{key}/branches", token=member, body=BRANCH)
    assert first.status_code == 202, first.text
    assert first.json()["operation"]["type"] == "branch.create"
    assert _rows(drive, key) == 1
    second = drive.call("POST", f"/v1/projects/{key}/branches", token=member, body=BRANCH)
    assert (second.status_code, second.json()) == (409, {"error": "branch_limit_reached"})
    assert _rows(drive, key) == 1

    _finish(drive, key)
    _record_branch(drive, key)
    restore = {**BRANCH, "branch": "qa", "target_time": "2026-10-14T08:00:00Z"}
    for path, body in (("branches", {**BRANCH, "branch": "qa"}), ("restores", restore)):
        again = drive.call("POST", f"/v1/projects/{key}/{path}", token=member, body=body)
        assert (again.status_code, again.json()) == (409, {"error": "branch_limit_reached"})
    assert _rows(drive, key) == 1

    arguments = json.dumps({**BRANCH, "branch": "qa"})
    direct = drive.cluster.run(
        f"SELECT * FROM app.control_request_operation('{org['users']['member']}', "
        f"'{org['id']}', '{key}', 'branch.create', '{arguments}'::jsonb)",
        as_role=drive.cluster.auth_role,
    )
    assert direct.returncode != 0 and "AP409: branch_limit_reached" in direct.stderr
    assert _rows(drive, key) == 1


def test_the_route_refuses_a_second_branch_without_asking_the_set(
    drive: Any, accepting: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ROUTE is a reader of its own (D2430): with a branch recorded live, and
    with a creation in flight, a second creation is refused `branch_limit_reached`
    and the control set's `control_request_operation` is never called -- the
    proof above holds the set's reader, this one the route's. The control: the
    same project with neither does reach the set.

    Goes red if: the route stops counting recorded branches or creations in
    flight, leaving the set as the only reader."""
    from app.control_repository import ControlRepository

    asked: list[str] = []
    real = ControlRepository.request_operation

    async def recording(self: Any, *arguments: Any, **named: Any) -> Any:
        asked.append(arguments[3])
        return await real(self, *arguments, **named)

    monkeypatch.setattr(ControlRepository, "request_operation", recording)
    live, flight, empty = _org(drive, "route-a"), _org(drive, "route-b"), _org(drive, "route-c")
    _record_branch(drive, live["project"])
    drive.cluster.query(
        "INSERT INTO app.control_operations (organization_id, project_key, type, status, "
        f"requested_by, arguments) VALUES ('{flight['id']}', '{flight['project']}', "
        f"'restore.create', 'running', '{flight['users']['member']}', '{{}}')"
    )
    for org in (live, flight):
        answer = drive.call("POST", f"/v1/projects/{org['project']}/branches",
                            token=org["tokens"]["member"], body=BRANCH)  # fmt: skip
        assert (answer.status_code, answer.json()) == (409, {"error": "branch_limit_reached"})
    assert asked == [], asked
    reached = drive.call("POST", f"/v1/projects/{empty['project']}/branches",
                         token=empty["tokens"]["member"], body=BRANCH)  # fmt: skip
    assert reached.status_code == 202 and asked == ["branch.create"], (reached.text, asked)


def test_a_foreign_and_a_missing_branch_answer_alike(drive: Any) -> None:
    """D2451: another organisation's project's branch, a project that does not
    exist and a branch the caller's own project does not have answer ONE
    `404` -- the same status and the same body, byte for byte; the caller's own
    live branch answers 200 (the control)."""
    mine, theirs = _org(drive, "enum-a"), _org(drive, "enum-b")
    _record_branch(drive, theirs["project"])
    token = mine["tokens"]["viewer"]
    answers = [
        drive.call("GET", f"/v1/projects/{theirs['project']}/branches/dev", token=token),
        drive.call("GET", "/v1/projects/nosuch1-prod/branches/dev", token=token),
        drive.call("GET", f"/v1/projects/{mine['project']}/branches/dev", token=token),
        drive.call("GET", f"/v1/projects/{theirs['project']}/branches", token=token),
    ]
    shapes = {(answer.status_code, answer.content) for answer in answers}
    assert shapes == {(404, b'{"error":"not_found"}')}, shapes
    own = drive.call(
        "GET", f"/v1/projects/{theirs['project']}/branches/dev", token=theirs["tokens"]["viewer"]
    )
    assert own.status_code == 200, own.text
    assert own.json()["name"] == "dev" and own.json()["state"] == "ready"
    assert "not backed up" in own.json()["notice"]


def test_a_project_with_a_branch_cannot_be_deleted(drive: Any, accepting: None) -> None:
    """D2438: an owner's deletion of a project with a live branch is `409
    conflict` and writes nothing; the control set refuses it on its own too.
    The control: the same deletion of a project without a branch is recorded."""
    org = _org(drive, "delete")
    key, owner = org["project"], org["tokens"]["owner"]
    _record_branch(drive, key)
    refused = drive.call("DELETE", f"/v1/projects/{key}", token=owner)
    assert (refused.status_code, refused.json()["error"]) == (409, "conflict"), refused.text
    assert _rows(drive, key) == 0
    direct = drive.cluster.run(
        f"SELECT * FROM app.control_request_operation('{org['users']['owner']}', "
        f"'{org['id']}', '{key}', 'project.delete', '{{}}'::jsonb)",
        as_role=drive.cluster.auth_role,
    )
    assert direct.returncode != 0 and "AP409: conflict" in direct.stderr

    other = _org(drive, "delete-ok")
    allowed = drive.call(
        "DELETE", f"/v1/projects/{other['project']}", token=other["tokens"]["owner"]
    )
    assert allowed.status_code == 202, allowed.text


def test_the_branch_routes_need_a_human_or_a_scoped_key(drive: Any, accepting: None) -> None:
    """D2468 (narrowing D2436): a key reads branches and backups with
    `projects:read`, and can create, restore, reset or delete NOTHING -- each
    write carries the branch's own credentials, so it is a person's
    (`human_session_required`). A viewer person may not create; a member may
    not delete a branch (admin); the owner may (the control)."""
    org = _org(drive, "roles")
    key = org["project"]
    reader = _key(drive, org, ["projects:read"])
    writer = _key(drive, org, ["projects:read", "projects:write"])
    for path in ("branches", "backups"):
        assert drive.call("GET", f"/v1/projects/{key}/{path}", token=reader).status_code == 200
    restore = {**BRANCH, "target_time": "2026-10-14T08:00:00Z"}
    for method, path, body in (
        ("POST", "branches", BRANCH),
        ("POST", "restores", restore),
        ("POST", "branches/dev/reset", {k: v for k, v in BRANCH.items() if k != "branch"}),
        ("DELETE", "branches/dev", None),
    ):
        answer = drive.call(method, f"/v1/projects/{key}/{path}", token=writer, body=body)
        assert (answer.status_code, answer.json()) == (403, {"error": "human_session_required"}), (
            path,
            answer.text,
        )
    viewer = drive.call("POST", f"/v1/projects/{key}/branches", token=org["tokens"]["viewer"],
                        body=BRANCH)  # fmt: skip
    assert viewer.status_code == 403, viewer.text
    assert _rows(drive, key) == 0

    _record_branch(drive, key)
    member = drive.call("DELETE", f"/v1/projects/{key}/branches/dev", token=org["tokens"]["member"])
    assert member.status_code == 403, member.text
    owner = drive.call("DELETE", f"/v1/projects/{key}/branches/dev", token=org["tokens"]["owner"])
    assert owner.status_code == 202, owner.text
    assert owner.json()["operation"]["type"] == "branch.delete"
    missing = drive.call(
        "DELETE", f"/v1/projects/{key}/branches/nosuch", token=org["tokens"]["owner"]
    )
    assert (missing.status_code, missing.json()) == (404, {"error": "not_found"})


def test_an_expiry_is_bounded_and_only_an_expiry_requests_without_a_member(
    drive: Any, accepting: None
) -> None:
    """ADR 0272: `expires_at` less than 15 minutes or more than 7 days ahead is
    `422` and writes nothing; a row a person requests is `origin = member`; the
    one function that writes `origin = expiry` is granted to nobody, writes ONE
    `branch.delete` for the member who set the expiry, and nothing while an
    operation is open (rig 40d); `origin = expiry` on another type is refused by
    the CHECK."""
    org = _org(drive, "expiry")
    key, member = org["project"], org["tokens"]["member"]
    now = datetime.now(UTC)
    for delta in (timedelta(minutes=5), timedelta(days=8)):
        stamp = (now + delta).strftime("%Y-%m-%dT%H:%M:%SZ")
        bad = drive.call("POST", f"/v1/projects/{key}/branches", token=member,
                         body={**BRANCH, "expires_at": stamp})  # fmt: skip
        assert bad.status_code == 422, (delta, bad.text)
    assert _rows(drive, key) == 0
    good = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    made = drive.call("POST", f"/v1/projects/{key}/branches", token=member,
                      body={**BRANCH, "expires_at": good})  # fmt: skip
    assert made.status_code == 202, made.text
    assert drive.cluster.query(
        f"SELECT origin FROM app.control_operations WHERE project_key = '{key}'"
    ) == ["member"]

    member_id = org["users"]["member"]
    _record_branch(drive, key, expires_at=(now - timedelta(minutes=1)).isoformat(),
                   expires_for=member_id)  # fmt: skip
    open_call = f"SELECT coalesce(app.control_request_expiry('{key}', 'dev')::text, 'NULL')"
    assert drive.cluster.query(open_call) == ["NULL"]  # the creation is still pending
    _finish(drive, key)
    first, second = drive.cluster.query(open_call), drive.cluster.query(open_call)
    assert first != ["NULL"] and second == ["NULL"], (first, second)
    expiry = drive.cluster.query(
        "SELECT type || ' ' || origin || ' ' || (requested_by = '" + member_id + "') "
        f"FROM app.control_operations WHERE project_key = '{key}' AND origin = 'expiry'"
    )
    assert expiry == ["branch.delete expiry true"], expiry
    denied = drive.cluster.run(
        f"SELECT app.control_request_expiry('{key}', 'dev')", as_role=drive.cluster.auth_role
    )
    # The FUNCTION's refusal, not a table's: the auth role holds no table either,
    # so "permission denied" alone would pass with the function granted.
    assert denied.returncode != 0, denied.stdout
    assert "permission denied for function control_request_expiry" in denied.stderr
    forged = drive.cluster.run(
        "INSERT INTO app.control_operations (organization_id, project_key, type, status, "
        f"requested_by, arguments, origin) VALUES ('{org['id']}', '{key}', 'project.sleep', "
        f"'succeeded', '{member_id}', '{{}}', 'expiry')"
    )
    assert forged.returncode != 0 and "control_operations_expiry_deletes_a_branch" in forged.stderr


def test_an_operation_read_names_its_origin(drive: Any, accepting: None) -> None:
    """D2480: `GET /v1/operations/{id}` and the organisation's list name each
    row's `origin` -- `member` for the branch a member asked for, `expiry` for
    the deletion `control_request_expiry` wrote on that member's behalf -- so a
    customer reads through `/v1` alone that the trigger fired (BR-LIVE-001)."""
    org = _org(drive, "origin")
    key, member = org["project"], org["tokens"]["member"]
    made = drive.call("POST", f"/v1/projects/{key}/branches", token=member, body=BRANCH)
    assert made.status_code == 202, made.text
    asked = made.json()["operation"]["id"]
    _finish(drive, key)
    expires = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    _record_branch(drive, key, expires_at=expires, expires_for=org["users"]["member"])
    (expired,) = drive.cluster.query(f"SELECT app.control_request_expiry('{key}', 'dev')::text")
    origins = {}
    for operation in (asked, expired):
        read = drive.call("GET", f"/v1/operations/{operation}", token=member)
        assert read.status_code == 200, read.text
        origins[read.json()["type"]] = read.json()["origin"]
    assert origins == {"branch.create": "member", "branch.delete": "expiry"}, origins
    listed = drive.call("GET", f"/v1/operations?organization={org['id']}", token=member)
    assert listed.status_code == 200, listed.text
    assert {r["id"]: r["origin"] for r in listed.json()["operations"]} == {
        asked: "member",
        expired: "expiry",
    }


def test_the_backups_route_serves_the_recorded_window(drive: Any) -> None:
    """ADR 0273 through the route: no reading is `could_not_determine`; a fresh
    reading with every status read is the window, its bounds the reading's; a
    reading with an undetermined status is `could_not_determine` naming it."""
    org = _org(drive, "backups")
    key, viewer = org["project"], org["tokens"]["viewer"]
    none = drive.call("GET", f"/v1/projects/{key}/backups", token=viewer)
    assert none.status_code == 200 and none.json()["status"] == "could_not_determine"
    reading = {
        "project_key": key, "repository_status": "ok", "archiver_status": "ok",
        "mirror_status": "ok", "earliest": "2026-10-12T10:39:27Z",
        "latest": "2026-10-14T08:17:25Z", "last_full_at": "2026-10-12T10:39:26Z",
    }  # fmt: skip
    drive.cluster.query(f"SELECT app.control_record_backups('{json.dumps([reading])}'::jsonb)")
    window = drive.call("GET", f"/v1/projects/{key}/backups", token=viewer).json()
    assert window["status"] == "window", window
    assert window["earliest"].startswith("2026-10-12T10:39:27")
    assert window["latest"].startswith("2026-10-14T08:17:25")
    unknown = {**reading, "archiver_status": "unknown", "reason": "the archiver did not answer"}
    drive.cluster.query(f"SELECT app.control_record_backups('{json.dumps([unknown])}'::jsonb)")
    undetermined = drive.call("GET", f"/v1/projects/{key}/backups", token=viewer).json()
    assert undetermined["status"] == "could_not_determine", undetermined
    assert "archiver" in undetermined["reason"]


def test_a_branch_write_is_not_available_until_its_row_is_reachable(drive: Any) -> None:
    """ADR 0254 in the product's own state: the branch rows are `planned` until
    Run 8, so a creation answers `409 not_available` naming `branches` and a
    restore naming `restore_to_branch` -- before the body is read, nothing
    recorded."""
    org = _org(drive, "planned")
    key, member = org["project"], org["tokens"]["member"]
    for path, row in (("branches", "branches"), ("restores", "restore_to_branch")):
        answer = drive.call("POST", f"/v1/projects/{key}/{path}", token=member,
                            body={"nonsense": secrets.token_hex(4)})  # fmt: skip
        assert (answer.status_code, answer.json()) == (
            409,
            {"error": "not_available", "ledger_row": row},
        ), answer.text
    assert _rows(drive, key) == 0
