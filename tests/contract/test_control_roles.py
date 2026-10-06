"""The organisation role matrix, route by route, against a real cluster.

CTL-ROLE-001 (ADR 0252, D2053): every `/v1` route answers as
`control_roles.MATRIX` says for every role -- and the table names every route
the application serves, in both directions; the last owner cannot be removed
or demoted; an admin cannot make an owner; a foreign organisation and a
missing one look the same. Run 5 extends the table and this module with the
keys, projects and operations routes.
"""

from __future__ import annotations

import uuid
from typing import Any

import control_cluster as cc
import pytest

from app import control_roles

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

ROLES = ("owner", "admin", "member", "viewer")


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Any:
    try:
        with cc.control_cluster() as cluster:
            with cc.control_app(cluster, tmp_path_factory.mktemp("control-roles")) as driver:
                yield driver
    except RuntimeError as exc:
        pytest.skip(str(exc))


@pytest.fixture(scope="module")
def org(drive: Any) -> dict[str, Any]:
    """One organisation with one person per role (owner and admin with a
    factor) and an outsider who belongs to another organisation."""
    people: dict[str, Any] = {"ids": {}, "tokens": {}}
    owner = drive.account("role-owner")
    people["id"] = drive.organization(owner, "the organisation")
    people["ids"]["owner"] = owner
    people["tokens"]["owner"] = drive.token("role-owner", drive.enable_factor(owner))
    for role in ("admin", "member", "viewer"):
        user = drive.account(f"role-{role}")
        drive.member(people["id"], user, role)
        people["ids"][role] = user
        seed = drive.enable_factor(user) if role == "admin" else None
        people["tokens"][role] = drive.token(f"role-{role}", seed)
    outsider = drive.account("role-outsider")
    people["foreign"] = drive.organization(outsider, "the outsider's own")
    people["tokens"]["outsider"] = drive.token("role-outsider", drive.enable_factor(outsider))
    return people


def _org_routes(drive: Any) -> dict[str, tuple[str, str]]:
    """Every route whose matrix entry is a role, by name -> (method, path)."""
    found: dict[str, tuple[str, str]] = {}
    for route in drive.application.routes:
        if getattr(route, "path", "").startswith("/v1/") and route.name in control_roles.MATRIX:
            if control_roles.MATRIX[route.name] in control_roles.ROLES:
                found[route.name] = (next(iter(route.methods)), route.path)
    return found


def _throwaway(drive: Any, org: str) -> str:
    """A fresh viewer to change or remove, so a permitted call does no harm."""
    user = drive.account(f"role-target-{uuid.uuid4().hex[:8]}")
    drive.member(org, user, "viewer")
    return user


def _invitation(drive: Any, org: dict[str, Any]) -> str:
    minted = drive.call(
        "POST", "/v1/invitations", token=org["tokens"]["owner"],
        body={"organization_id": org["id"], "role": "viewer"},
    )  # fmt: skip
    assert minted.status_code == 201, minted.text
    return minted.json()["id"]


def _call(drive: Any, org: dict[str, Any], name: str, who: str) -> int:
    method, path = _org_routes(drive)[name]
    filled = path.replace("{organization}", org["id"])
    body = None
    if "{user}" in filled:
        filled = filled.replace("{user}", _throwaway(drive, org["id"]))
        body = {"role": "viewer"} if method == "PATCH" else None
    if "{invitation}" in filled:
        filled = filled.replace("{invitation}", _invitation(drive, org))
    return drive.call(method, filled, token=org["tokens"][who], body=body).status_code


def test_every_route_and_role_answers_as_the_matrix_says(drive: Any, org: dict[str, Any]) -> None:
    # The table names every management route the application serves, and only those.
    served = {
        route.name for route in drive.application.routes
        if getattr(route, "path", "").startswith("/v1/")
    }  # fmt: skip
    assert served == set(control_roles.MATRIX), served ^ set(control_roles.MATRIX)

    routes = _org_routes(drive)
    assert routes, "no organisation route found -- this test would measure nothing"
    wrong: list[str] = []
    for name in sorted(routes):
        minimum = control_roles.MATRIX[name]
        for who in (*ROLES, "outsider"):
            status = _call(drive, org, name, who)
            if who == "outsider":
                expected_refusal = 404
            elif control_roles.rank(who) < control_roles.rank(minimum):
                expected_refusal = 403
            else:
                expected_refusal = None
            if expected_refusal is None and status in (401, 403, 404):
                wrong.append(f"{name} as {who}: refused {status}, the matrix allows it")
            if expected_refusal is not None and status != expected_refusal:
                wrong.append(f"{name} as {who}: {status}, expected {expected_refusal}")
    assert not wrong, "\n".join(wrong)

    # The ACCOUNT routes refuse nobody signed in; the PUBLIC ones need no bearer.
    for who in (*ROLES, "outsider"):
        assert drive.call("GET", "/v1/organizations", token=org["tokens"][who]).status_code == 200
    assert drive.call("GET", "/v1/organizations").status_code == 401


def test_the_last_owner_stays(drive: Any, org: dict[str, Any]) -> None:
    owner_token = org["tokens"]["owner"]
    path = f"/v1/organizations/{org['id']}/members/{org['ids']['owner']}"
    demoted = drive.call("PATCH", path, token=owner_token, body={"role": "admin"})
    assert (demoted.status_code, demoted.json()) == (409, {"error": "last_owner"})
    removed = drive.call("DELETE", path, token=owner_token)
    assert (removed.status_code, removed.json()) == (409, {"error": "last_owner"})

    # Control: with a second owner, the first may step down.
    second = _throwaway(drive, org["id"])
    promoted = drive.call(
        "PATCH", f"/v1/organizations/{org['id']}/members/{second}",
        token=owner_token, body={"role": "owner"},
    )  # fmt: skip
    assert promoted.status_code == 200, promoted.text
    stepped = drive.call(
        "PATCH", f"/v1/organizations/{org['id']}/members/{second}",
        token=owner_token, body={"role": "viewer"},
    )  # fmt: skip
    assert stepped.status_code == 200, stepped.text


def test_an_admin_cannot_make_an_owner(drive: Any, org: dict[str, Any]) -> None:
    admin = org["tokens"]["admin"]
    target = _throwaway(drive, org["id"])
    members = f"/v1/organizations/{org['id']}/members"
    for method, path, body in (
        ("PATCH", f"{members}/{target}", {"role": "owner"}),
        ("PATCH", f"{members}/{org['ids']['owner']}", {"role": "admin"}),
        ("DELETE", f"{members}/{org['ids']['owner']}", None),
        ("POST", "/v1/invitations", {"organization_id": org["id"], "role": "owner"}),
    ):
        refused = drive.call(method, path, token=admin, body=body)
        assert (refused.status_code, refused.json()) == (
            403,
            {"error": "authorization_failed"},
        ), (method, path)
    # Control: the same admin may make an admin.
    allowed = drive.call("PATCH", f"{members}/{target}", token=admin, body={"role": "admin"})
    assert allowed.status_code == 200, allowed.text


def test_a_foreign_id_and_a_missing_id_look_the_same(drive: Any, org: dict[str, Any]) -> None:
    viewer = org["tokens"]["viewer"]
    answers = [
        drive.call("GET", f"/v1/organizations/{target}", token=viewer)
        for target in (org["foreign"], str(uuid.uuid4()), "not-a-uuid")
    ]
    shapes = {(response.status_code, response.content) for response in answers}
    assert shapes == {(404, b'{"error":"not_found"}')}, shapes
    # Control: the viewer's own organisation answers.
    assert drive.call("GET", f"/v1/organizations/{org['id']}", token=viewer).status_code == 200
