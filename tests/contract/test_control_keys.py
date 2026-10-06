"""Management API keys, against a real cluster (KEY-MINT-001, ADR 0253, D2052).

A key is `apg_<16 hex>_<43>`, shown once and stored as its id and the SHA-256
of its secret. Its scopes are bounded by the Session 37 vocabulary and by the
minter's role; it mints nothing (`human_session_required`); its authority on
every request is its scopes intersected with its owner's CURRENT role, inside
its own organisation; a revoked key and a departed owner's key are refused on
the next request with the one answer an unknown key gets.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

import control_cluster as cc
import pytest

from app import control_roles

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

KEY_SHAPE = re.compile(r"^apg_([0-9a-f]{16})_([A-Za-z0-9_-]{43})$")
REFUSED = (401, b'{"error":"authentication_failed"}')


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Any:
    try:
        with cc.control_cluster() as cluster:
            with cc.control_app(cluster, tmp_path_factory.mktemp("control-keys")) as driver:
                yield driver
    except RuntimeError as exc:
        pytest.skip(str(exc))


@pytest.fixture(scope="module")
def org(drive: Any) -> dict[str, Any]:
    """Organisation A (an owner and an admin, each with a factor, and two
    members) and organisation B, which one of A's members also belongs to;
    a project adopted into each."""
    people: dict[str, Any] = {"ids": {}, "tokens": {}}
    owner = drive.account("key-owner")
    people["a"] = drive.organization(owner, "a")
    people["ids"]["owner"] = owner
    people["tokens"]["owner"] = drive.token("key-owner", drive.enable_factor(owner))
    admin = drive.account("key-admin")
    drive.member(people["a"], admin, "admin")
    people["ids"]["admin"] = admin
    people["tokens"]["admin"] = drive.token("key-admin", drive.enable_factor(admin))
    for name in ("member", "sibling"):
        user = drive.account(f"key-{name}")
        drive.member(people["a"], user, "member")
        people["ids"][name] = user
        people["tokens"][name] = drive.token(f"key-{name}")
    other = drive.account("key-other-owner")
    people["b"] = drive.organization(other, "b")
    drive.member(people["b"], people["ids"]["member"], "viewer")
    for key, organization in (("alpha-prod", people["a"]), ("beta-prod", people["b"])):
        drive.cluster.query(
            f"SELECT app.control_adopt_project('{key}', '{organization}', "
            f"'{key.split('-')[0]}', 'prod', '{key}.test', '1.15.0', 'abc');"
        )
    return people


def _mint(drive: Any, token: str, organization: str, scopes: list[str], name: str = "k") -> Any:
    return drive.call(
        "POST", f"/v1/organizations/{organization}/keys", token=token,
        body={"name": name, "scopes": scopes},
    )  # fmt: skip


def _key(drive: Any, token: str, organization: str, scopes: list[str]) -> str:
    minted = _mint(drive, token, organization, scopes)
    assert minted.status_code == 201, minted.text
    return minted.json()["key"]


def test_a_key_is_shown_once_and_stored_hashed(drive: Any, org: dict[str, Any]) -> None:
    minted = _mint(drive, org["tokens"]["member"], org["a"], ["projects:read"], name="ci")
    assert minted.status_code == 201, minted.text
    assert minted.headers["cache-control"] == "no-store"
    body = minted.json()
    match = KEY_SHAPE.match(body["key"])
    assert match is not None, body["key"]
    key_id, secret = match.groups()
    assert (body["key_id"], body["scopes"]) == (key_id, ["projects:read"])

    row = drive.cluster.query(
        "SELECT secret_sha256 || '|' || row_to_json(k)::text FROM app.control_keys k "  # noqa: S608
        f"WHERE key_id = '{key_id}';"
    )[0]
    stored, whole = row.split("|", 1)
    assert stored == hashlib.sha256(secret.encode("utf-8")).hexdigest()
    assert secret not in whole and body["key"] not in whole

    listed = drive.call("GET", f"/v1/organizations/{org['a']}/keys", token=org["tokens"]["member"])
    assert listed.status_code == 200, listed.text
    assert key_id in listed.text
    assert secret not in listed.text and stored not in listed.text


def test_scopes_are_bounded_by_the_vocabulary_and_the_role(
    drive: Any, org: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    member = org["tokens"]["member"]
    for scopes in (["projects:write"], ["admin_users:write"], ["projects:read", "keys:write"]):
        refused = _mint(drive, member, org["a"], scopes)
        assert refused.status_code == 422, (scopes, refused.text)
    empty = _mint(drive, member, org["a"], [])
    assert empty.status_code == 400, empty.text

    # Session 37 grants every role every read scope (D2053), so the role half
    # binds nothing in the product today -- asserted, so the day it does this
    # module is read again -- and is proved with a role table that differs.
    assert all(
        scopes == frozenset(control_roles.KEY_VOCABULARY)
        for scopes in control_roles.ROLE_SCOPES.values()
    )
    narrowed = dict(control_roles.ROLE_SCOPES)
    narrowed["member"] = frozenset({"projects:read", "organizations:read"})
    monkeypatch.setattr(control_roles, "ROLE_SCOPES", narrowed)
    beyond = _mint(drive, member, org["a"], ["members:read"])
    assert beyond.status_code == 422, beyond.text
    # Control: within the narrowed role, the same member mints.
    assert _mint(drive, member, org["a"], ["projects:read"]).status_code == 201


def test_a_key_mints_nothing(drive: Any, org: dict[str, Any]) -> None:
    key = _key(drive, org["tokens"]["admin"], org["a"], list(control_roles.KEY_VOCABULARY))
    member = org["ids"]["member"]
    for method, path, body in (
        ("POST", f"/v1/organizations/{org['a']}/keys", {"name": "x", "scopes": ["projects:read"]}),
        ("GET", f"/v1/organizations/{org['a']}/keys", None),
        ("POST", "/v1/invitations", {"organization_id": org["a"], "role": "viewer"}),
        ("POST", "/v1/me/totp", None),
        ("GET", "/v1/me", None),
        ("PATCH", f"/v1/organizations/{org['a']}/members/{member}", {"role": "viewer"}),
        ("POST", "/v1/organizations", {"name": "made by a key"}),
    ):
        refused = drive.call(method, path, token=key, body=body)
        assert (refused.status_code, refused.json()) == (
            403,
            {"error": "human_session_required"},
        ), (method, path)
    # Control: the same key reads what its scopes name.
    assert drive.call("GET", "/v1/projects", token=key).status_code == 200


def test_a_demotion_narrows_a_key(
    drive: Any, org: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The intersection is computed per request from the owner's CURRENT role.

    With D2053's table every role grants the same reads, so a demotion
    narrows nothing in Session 37; the mechanism is proved with a table in
    which `viewer` lacks `members:read` (D2109)."""
    narrowed = dict(control_roles.ROLE_SCOPES)
    narrowed["viewer"] = frozenset({"projects:read", "organizations:read", "operations:read"})
    monkeypatch.setattr(control_roles, "ROLE_SCOPES", narrowed)

    target = drive.account(f"key-demoted-{uuid.uuid4().hex[:6]}")
    drive.member(org["a"], target, "member")
    token = drive.token(target_name(drive, target))
    key = _key(drive, token, org["a"], ["members:read", "projects:read"])
    members = f"/v1/organizations/{org['a']}/members"
    assert drive.call("GET", members, token=key).status_code == 200

    demoted = drive.call(
        "PATCH", f"{members}/{target}", token=org["tokens"]["owner"], body={"role": "viewer"}
    )
    assert demoted.status_code == 200, demoted.text
    narrowed_answer = drive.call("GET", members, token=key)
    assert (narrowed_answer.status_code, narrowed_answer.json()) == (
        403,
        {"error": "authorization_failed"},
    )
    # Control: the scope the viewer role still grants still works.
    assert drive.call("GET", "/v1/projects", token=key).status_code == 200


def target_name(drive: Any, user: str) -> str:
    return drive.cluster.query(
        f"SELECT username FROM app.control_accounts WHERE user_id = '{user}';"  # noqa: S608
    )[0]


def test_a_revoked_key_and_a_departed_owners_key_are_refused(
    drive: Any, org: dict[str, Any]
) -> None:
    member, sibling = org["tokens"]["member"], org["tokens"]["sibling"]
    revoked = _key(drive, member, org["a"], ["projects:read"])
    assert drive.call("GET", "/v1/projects", token=revoked).status_code == 200
    key_id = KEY_SHAPE.match(revoked).group(1)  # type: ignore[union-attr]
    gone = drive.call("DELETE", f"/v1/organizations/{org['a']}/keys/{key_id}", token=member)
    assert gone.status_code == 204, gone.text

    leaver = drive.account(f"key-leaver-{uuid.uuid4().hex[:6]}")
    drive.member(org["a"], leaver, "member")
    departed = _key(drive, drive.token(target_name(drive, leaver)), org["a"], ["projects:read"])
    assert drive.call("GET", "/v1/projects", token=departed).status_code == 200
    removed = drive.call(
        "DELETE", f"/v1/organizations/{org['a']}/members/{leaver}", token=org["tokens"]["admin"]
    )
    assert removed.status_code == 204, removed.text

    sibling_key = _key(drive, sibling, org["a"], ["projects:read"])
    wrong_secret = revoked[:-1] + ("A" if revoked[-1] != "A" else "B")
    unknown = "apg_" + "0" * 16 + "_" + "A" * 43
    shapes = {
        name: (r.status_code, r.content)
        for name, r in (
            (name, drive.call("GET", "/v1/projects", token=token))
            for name, token in (
                ("revoked", revoked),
                ("departed", departed),
                ("unknown", unknown),
                ("malformed", "apg_not-a-key"),
                ("wrong secret", wrong_secret),
            )
        )
    }
    assert set(shapes.values()) == {REFUSED}, shapes
    # Control: a sibling member's key, minted the same way, is served.
    assert drive.call("GET", "/v1/projects", token=sibling_key).status_code == 200


def test_a_key_reaches_no_other_organisation(drive: Any, org: dict[str, Any]) -> None:
    """The member belongs to A and B; a key minted in A sees A alone."""
    key = _key(drive, org["tokens"]["member"], org["a"], list(control_roles.KEY_VOCABULARY))
    a, b = org["a"], org["b"]
    for path in (
        f"/v1/organizations/{b}",
        f"/v1/organizations/{b}/members",
        f"/v1/projects?organization={b}",
        f"/v1/operations?organization={b}",
        "/v1/projects/beta-prod",
    ):
        refused = drive.call("GET", path, token=key)
        assert (refused.status_code, refused.content) == (404, b'{"error":"not_found"}'), path
    listed = drive.call("GET", "/v1/organizations", token=key).json()["organizations"]
    assert [row["id"] for row in listed] == [a]
    projects = drive.call("GET", "/v1/projects", token=key).json()["projects"]
    assert [row["key"] for row in projects] == ["alpha-prod"]
    # Control: the member's own SESSION sees both organisations.
    session = drive.call("GET", "/v1/organizations", token=org["tokens"]["member"]).json()
    assert {row["id"] for row in session["organizations"]} == {a, b}
