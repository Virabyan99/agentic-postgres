"""The project writes of `/v1`, against a real cluster (OPN-REQ-001; ADR 0256, D2165).

What a member's request does before the reconciler is involved: the slot
reading refuses a creation BEFORE any row (D2160); one non-terminal operation
per project and one creation per organisation, held by the database itself
(D2166); the roles and the keys (D2165); the download URL handed once (D2164);
cancelling (D2067); a project's state read from its history (D2159).

Every operation type is planned in the ledger until Run 10 (ADR 0254), so the
routes answer `not_available` in the product; these proofs accept the six types
for their own duration (`accepting`) -- the refusal itself is
`test_operation_types.py`'s. The reconciler's half is played by the superuser
calling the set's invoker functions, as the reconciler will.
"""

# ruff: noqa: S608 -- every interpolated value is a uuid or a key this module
# wrote, run against a throwaway cluster.

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from typing import Any

import control_cluster as cc
import pytest

from app import compute_profiles, control_roles, operations

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

HANDOFF = hashlib.sha256(b"a handoff token the CLI keeps").hexdigest()


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Any:
    try:
        with cc.control_cluster() as cluster:
            with cc.control_app(cluster, tmp_path_factory.mktemp("control-projects")) as driver:
                yield driver
    except RuntimeError as exc:
        pytest.skip(str(exc))


@pytest.fixture
def accepting(monkeypatch: pytest.MonkeyPatch) -> None:
    """The six types accepted, for this proof only. Since Run 10 the module
    accepts them itself (their rows are `trial`, ADR 0261); the pin stays so
    these proofs of the routes do not move when Run 13 resolves a row back to
    `planned` -- the gate's own proof is `test_operation_types`'."""
    monkeypatch.setattr(operations, "ACCEPTED_TYPES", operations.EXECUTED_TYPES)


def _org(drive: Any, label: str) -> dict[str, Any]:
    """An organisation with one person per role and a project adopted into it."""
    people: dict[str, Any] = {"ids": {}, "tokens": {}}
    tag = f"{label}-{uuid.uuid4().hex[:6]}"
    owner = drive.account(f"{tag}-owner")
    people["id"] = drive.organization(owner, tag)
    people["ids"]["owner"] = owner
    people["tokens"]["owner"] = drive.token(f"{tag}-owner", drive.enable_factor(owner))
    for role in ("admin", "member", "viewer"):
        user = drive.account(f"{tag}-{role}")
        drive.member(people["id"], user, role)
        people["ids"][role] = user
        seed = drive.enable_factor(user) if role == "admin" else None
        people["tokens"][role] = drive.token(f"{tag}-{role}", seed)
    people["project"] = _adopt(drive, people["id"])
    return people


def _adopt(drive: Any, organization: str) -> str:
    key = f"p{uuid.uuid4().hex[:8]}-prod"
    drive.cluster.query(
        f"SELECT app.control_adopt_project('{key}', '{organization}', '{key[:9]}', 'prod', "
        f"'{key}.test', '1.16.0', 'abc', 'eu-hel-1', 'small', NULL, "
        f"'https://{key}.test/api/app')"
    )
    return key


def _slots(drive: Any, state: str = "ready", *, minutes_ago: int = 0) -> None:
    reading = [{"key": "slot1-prod", "state": state, "region_id": "eu-hel-1"}]
    drive.cluster.query(f"SELECT app.control_record_slots('{json.dumps(reading)}'::jsonb)")
    if minutes_ago:
        drive.cluster.query(
            f"UPDATE app.control_slots SET observed_at = now() - interval '{minutes_ago} minutes'"
        )


def _create(drive: Any, token: str, organization: str, **changes: Any) -> Any:
    body = {
        "organization": organization,
        "name": "Shop backend",
        "profile": "small",
        "admin_username": "shop.admin",
        "handoff_sha256": HANDOFF,
        **changes,
    }
    return drive.call("POST", "/v1/projects", token=token, body=body)


def _count(drive: Any, where: str = "true") -> int:
    return int(drive.cluster.query(f"SELECT count(*) FROM app.control_operations WHERE {where}")[0])


def _finish_all(drive: Any) -> None:
    """The reconciler's half: claim and finish every pending row, succeeded."""
    while True:
        claimed = drive.cluster.query("SELECT id FROM app.control_claim_operation('test')")
        if not claimed:
            return
        drive.cluster.query(
            f"SELECT app.control_finish_operation('{claimed[0]}', 'succeeded', NULL, NULL)"
        )


def test_no_ready_slot_refuses_before_a_row(drive: Any, accepting: None) -> None:
    """D2160: `capacity_exhausted {reason: no_slot}` with nothing recorded --
    no reading, no ready slot, or a reading older than ten minutes."""
    org = _org(drive, "noslot")
    member = org["tokens"]["member"]
    drive.cluster.query("DELETE FROM app.control_slots")
    before = _count(drive)
    for prepare in (
        lambda: None,
        lambda: _slots(drive, "consumed"),
        lambda: _slots(drive, "ready", minutes_ago=11),
    ):
        prepare()
        refused = _create(drive, member, org["id"])
        assert refused.status_code == 409, refused.text
        body = refused.json()
        assert (body["error"], body["reason"]) == ("capacity_exhausted", "no_slot"), body
        assert "No resources were created." in body["message"]
        assert _count(drive) == before
    assert "ten minutes" in refused.json()["message"]
    # Control: a fresh ready reading, and the same request is recorded.
    _slots(drive)
    accepted = _create(drive, member, org["id"])
    assert accepted.status_code == 202, accepted.text
    operation = accepted.json()["operation"]
    assert (operation["type"], operation["status"], operation["project_key"]) == (
        "project.create",
        "pending",
        None,
    )
    assert _count(drive) == before + 1
    stored = drive.cluster.query(
        f"SELECT arguments::text FROM app.control_operations WHERE id = '{operation['id']}'"
    )[0]
    assert json.loads(stored) == {
        "name": "Shop backend",
        "profile": "small",
        "admin_username": "shop.admin",
        "handoff_sha256": HANDOFF,
    }
    _finish_all(drive)


def test_one_operation_at_a_time(drive: Any, accepting: None) -> None:
    """D2166: a second creation in the organisation, or a second write on a
    project, answers `conflict` naming the one in flight -- and the database
    itself refuses a second non-terminal row, which is what holds under a race."""
    org = _org(drive, "serial")
    member = org["tokens"]["member"]
    _slots(drive)
    first = _create(drive, member, org["id"]).json()["operation"]["id"]
    again = _create(drive, org["tokens"]["admin"], org["id"], name="Another")
    assert (again.status_code, again.json()) == (409, {"error": "conflict", "operation": first})

    project = org["project"]
    slept = drive.call("POST", f"/v1/projects/{project}/sleep", token=member)
    assert slept.status_code == 202, slept.text
    asleep = slept.json()["operation"]["id"]
    woken = drive.call("POST", f"/v1/projects/{project}/wake", token=member)
    assert (woken.status_code, woken.json()) == (409, {"error": "conflict", "operation": asleep})

    user, organization = org["ids"]["member"], org["id"]
    for duplicate in (
        f"('{organization}', NULL, 'project.create', '{user}', '{{}}'::jsonb)",
        f"('{organization}', '{project}', 'project.wake', '{user}', '{{}}'::jsonb)",
    ):
        inserted = drive.cluster.run(
            "INSERT INTO app.control_operations "
            f"(organization_id, project_key, type, requested_by, arguments) VALUES {duplicate}"
        )
        assert inserted.returncode != 0 and "duplicate key" in inserted.stderr, duplicate

    # Control: once both finish, each may be requested again.
    _finish_all(drive)
    assert _create(drive, member, org["id"]).status_code == 202
    assert drive.call("POST", f"/v1/projects/{project}/wake", token=member).status_code == 202
    _finish_all(drive)


def test_the_roles_decide_who_writes(drive: Any, accepting: None) -> None:
    """D2165: viewer reads only; member and above write; delete is admin and
    above; a key reaches sleep, wake and resize with `projects:write` and
    nothing else."""
    org = _org(drive, "roles")
    project, tokens = org["project"], org["tokens"]
    _slots(drive)
    writes = {
        "sleep": ("POST", f"/v1/projects/{project}/sleep", None),
        "resize": ("PUT", f"/v1/projects/{project}/compute", {"profile": "standard"}),
        "export": ("POST", f"/v1/projects/{project}/export", None),
        "delete": ("DELETE", f"/v1/projects/{project}", None),
    }
    for name, (method, path, body) in writes.items():
        viewer = drive.call(method, path, token=tokens["viewer"], body=body)
        assert (viewer.status_code, viewer.json()) == (
            403,
            {"error": "authorization_failed"},
        ), name
    assert _create(drive, tokens["viewer"], org["id"]).status_code == 403
    member_delete = drive.call("DELETE", f"/v1/projects/{project}", token=tokens["member"])
    assert member_delete.status_code == 403, member_delete.text

    minted = drive.call(
        "POST", f"/v1/organizations/{org['id']}/keys", token=tokens["member"],
        body={"name": "automation", "scopes": ["projects:read", "projects:write"]},
    )  # fmt: skip
    assert minted.status_code == 201, minted.text
    key = minted.json()["key"]
    for name in ("export", "delete"):
        method, path, body = writes[name]
        refused = drive.call(method, path, token=key, body=body)
        assert (refused.status_code, refused.json()) == (
            403,
            {"error": "human_session_required"},
        ), name
    by_key = _create(drive, key, org["id"])
    assert (by_key.status_code, by_key.json()) == (403, {"error": "human_session_required"})
    assert _count(drive, f"organization_id = '{org['id']}'") == 0

    # Control: the key sleeps the project; the admin deletes it once that is done.
    assert drive.call("POST", f"/v1/projects/{project}/sleep", token=key).status_code == 202
    _finish_all(drive)
    deleted = drive.call("DELETE", f"/v1/projects/{project}", token=tokens["admin"])
    assert deleted.status_code == 202, deleted.text
    assert deleted.json()["operation"]["type"] == "project.delete"
    _finish_all(drive)


def test_a_resize_says_the_restart_has_not_been_measured(drive: Any, accepting: None) -> None:
    """D2157: the `202` carries the resize sentence, and while no window is
    measured it prints no number."""
    org = _org(drive, "resize")
    path = f"/v1/projects/{org['project']}/compute"
    malformed = drive.call("PUT", path, token=org["tokens"]["member"], body={"profile": "huge"})
    assert malformed.status_code == 400, malformed.text
    answered = drive.call("PUT", path, token=org["tokens"]["member"], body={"profile": "large"})
    assert answered.status_code == 202, answered.text
    assert compute_profiles.RESIZE_WINDOW_SECONDS is None
    assert answered.json()["message"] == compute_profiles.UNMEASURED_RESIZE_MESSAGE
    assert not any(ch.isdigit() for ch in answered.json()["message"])
    stored = drive.cluster.query(
        "SELECT arguments::text FROM app.control_operations "
        f"WHERE id = '{answered.json()['operation']['id']}'"
    )[0]
    assert json.loads(stored) == {"profile": "large"}
    _finish_all(drive)


def test_the_download_url_is_returned_once(drive: Any, accepting: None) -> None:
    """D2164: the requester's first read carries `download_url`; the second
    does not, and neither does anyone else's read or any list."""
    org = _org(drive, "export")
    member, admin = org["tokens"]["member"], org["tokens"]["admin"]
    requested = drive.call("POST", f"/v1/projects/{org['project']}/export", token=member)
    assert requested.status_code == 202, requested.text
    operation = requested.json()["operation"]["id"]
    url = f"https://storage.invalid/exports/{operation}.dump?X-Amz-Expires=900&sig={secrets.token_hex(8)}"
    claimed = drive.cluster.query("SELECT id FROM app.control_claim_operation('test')")
    assert claimed == [operation]
    drive.cluster.query(
        f"SELECT app.control_finish_operation('{operation}', 'succeeded', NULL, "
        f"'{{\"size_bytes\": 1024}}'::jsonb, '{url}')"
    )

    path = f"/v1/operations/{operation}"
    by_admin = drive.call("GET", path, token=admin)
    listed = drive.call("GET", f"/v1/operations?organization={org['id']}", token=member)
    assert by_admin.status_code == 200 and "download_url" not in by_admin.json()
    assert url not in listed.text
    first = drive.call("GET", path, token=member)
    assert first.status_code == 200, first.text
    assert first.json()["download_url"] == url
    assert first.headers["cache-control"] == "no-store"
    second = drive.call("GET", path, token=member)
    assert second.status_code == 200 and "download_url" not in second.json()
    assert drive.cluster.query(
        f"SELECT result_secret IS NULL FROM app.control_operations WHERE id = '{operation}'"
    ) == ["t"]


def test_a_pending_operation_is_cancelled_by_its_requester_or_an_admin(
    drive: Any, accepting: None
) -> None:
    org = _org(drive, "cancel")
    tokens, project = org["tokens"], org["project"]
    requested = drive.call("POST", f"/v1/projects/{project}/sleep", token=tokens["member"])
    operation = requested.json()["operation"]["id"]
    cancel = f"/v1/operations/{operation}/cancel"
    assert drive.call("POST", cancel, token=tokens["viewer"]).status_code == 403
    cancelled = drive.call("POST", cancel, token=tokens["member"])
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["operation"]["status"] == "cancelled"
    again = drive.call("POST", cancel, token=tokens["member"])
    assert (again.status_code, again.json()) == (409, {"error": "conflict", "operation": operation})

    # An admin cancels another member's pending row; a running one is not cancelled.
    second = drive.call("POST", f"/v1/projects/{project}/sleep", token=tokens["member"])
    second_id = second.json()["operation"]["id"]
    assert (
        drive.call("POST", f"/v1/operations/{second_id}/cancel", token=tokens["admin"]).json()[
            "operation"
        ]["status"]
        == "cancelled"
    )
    third = drive.call("POST", f"/v1/projects/{project}/sleep", token=tokens["member"])
    third_id = third.json()["operation"]["id"]
    drive.cluster.query("SELECT id FROM app.control_claim_operation('test')")
    running = drive.call("POST", f"/v1/operations/{third_id}/cancel", token=tokens["member"])
    assert running.status_code == 409, running.text
    _finish_all(drive)
    drive.cluster.query(
        f"SELECT app.control_finish_operation('{third_id}', 'succeeded', NULL, NULL)"
    )


def test_a_project_reads_its_state_from_its_history(drive: Any, accepting: None) -> None:
    """D2159: an adopted project with no operation is `ready` and the
    operator's; after a sleep it is `sleeping`; after an interrupted wake it
    is `unknown` -- never `ready`."""
    org = _org(drive, "state")
    project, member = org["project"], org["tokens"]["member"]

    def read() -> dict[str, Any]:
        answer = drive.call("GET", f"/v1/projects/{project}", token=member)
        assert answer.status_code == 200, answer.text
        listed = drive.call("GET", f"/v1/projects?organization={org['id']}", token=member)
        assert [row for row in listed.json()["projects"] if row["key"] == project] == [
            answer.json()
        ]
        return answer.json()

    first = read()
    assert (first["state"], first["managed_by"]) == ("ready", "operator")
    assert (first["region"], first["profile"], first["app_route"]) == (
        "eu-hel-1",
        "small",
        f"https://{project}.test/api/app",
    )
    drive.call("POST", f"/v1/projects/{project}/sleep", token=member)
    # Pending: nothing has run, so the state is the one before it.
    assert (read()["state"], read()["managed_by"]) == ("ready", "operator")
    _finish_all(drive)
    assert (read()["state"], read()["managed_by"]) == ("sleeping", "reconciler")

    woken = drive.call("POST", f"/v1/projects/{project}/wake", token=member).json()["operation"]
    drive.cluster.query("SELECT id FROM app.control_claim_operation('test')")
    assert read()["state"] == "starting"
    drive.cluster.query(
        f"SELECT app.control_finish_operation('{woken['id']}', 'failed', 'interrupted', "
        '\'{"step": "start"}\'::jsonb)'
    )
    assert read()["state"] == "unknown"


def test_a_deleted_project_takes_no_more_writes(drive: Any, accepting: None) -> None:
    org = _org(drive, "deleted")
    project, admin = org["project"], org["tokens"]["admin"]
    drive.cluster.query(f"SELECT app.control_mark_deleted('{project}')")
    for method, path in (
        ("POST", f"/v1/projects/{project}/wake"),
        ("DELETE", f"/v1/projects/{project}"),
    ):
        refused = drive.call(method, path, token=admin)
        assert (refused.status_code, refused.json()) == (404, {"error": "not_found"}), path
    # Control: the record stays readable, with its deletion.
    kept = drive.call("GET", f"/v1/projects/{project}", token=admin).json()
    assert kept["deleted_at"] is not None


def test_no_string_produces_plan_limit_reached() -> None:
    """D2160: no entitlement code exists in Session 38."""
    for root in ("services", "src", "bin"):
        for path in (cc.REPO_ROOT / root).rglob("*"):
            if path.is_file() and path.suffix in {".py", ".sh", ".sql", ".json", ".yaml"}:
                assert "plan_limit_reached" not in path.read_text(encoding="utf-8"), path


def test_every_write_route_has_a_role_and_a_type() -> None:
    """The handler's table and the matrix agree: every write is a served,
    ACCOUNT route, needs a role, and (but cancel) requests an executed type."""
    for route, role in control_roles.PROJECT_WRITES.items():
        assert control_roles.MATRIX[route] == control_roles.ACCOUNT, route
        assert role in control_roles.ROLES, route
    assert set(control_roles.OPERATION_OF_ROUTE) == set(control_roles.PROJECT_WRITES) - {
        "cancel_operation"
    }
    assert set(control_roles.OPERATION_OF_ROUTE.values()) == operations.EXECUTED_TYPES
    assert {r for r, s in control_roles.KEY_SCOPES.items() if s == "projects:write"} == {
        "sleep_project",
        "wake_project",
        "resize_project",
    }
