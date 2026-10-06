"""Invitations, against a real cluster (CTL-INV-001, ADR 0252, D2051, D2099).

Minting is bounded by who mints: the registry administrator with a factor for
an account invitation, an admin or owner for a role at or below their own. The
token is shown once and stored as its SHA-256. Acceptance creates the account
and the membership in ONE transaction, exactly one of two concurrent
acceptances succeeds, every token that cannot be spent gets one byte-identical
answer, and a taken username leaves the token unspent.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

import control_cluster as cc
import pytest

from app import one_time_tokens

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Any:
    try:
        with cc.control_cluster() as cluster:
            with cc.control_app(cluster, tmp_path_factory.mktemp("control-invitations")) as driver:
                yield driver
    except RuntimeError as exc:
        pytest.skip(str(exc))


@pytest.fixture(scope="module")
def team(drive: Any) -> dict[str, Any]:
    """An organisation with an owner and an admin (each with a factor), a member
    and a viewer, and a registry administrator with a factor. Tokens cached:
    each login spends a step of its person's factor."""
    people: dict[str, Any] = {"ids": {}, "tokens": {}}
    owner = drive.account("inv-owner")
    org = drive.organization(owner)
    people["org"] = org
    people["ids"]["owner"] = owner
    people["tokens"]["owner"] = drive.token("inv-owner", drive.enable_factor(owner))
    for role in ("admin", "member", "viewer"):
        user = drive.account(f"inv-{role}")
        drive.member(org, user, role)
        people["ids"][role] = user
        seed = drive.enable_factor(user) if role == "admin" else None
        people["tokens"][role] = drive.token(f"inv-{role}", seed)
    registrar = drive.account("inv-registrar", admin=True)
    people["tokens"]["registrar"] = drive.token("inv-registrar", drive.enable_factor(registrar))
    drive.account("inv-outsider")
    people["tokens"]["outsider"] = drive.token("inv-outsider")
    return people


def _mint(drive: Any, token: str, org: str | None = None, role: str | None = None) -> Any:
    body: dict[str, Any] = {} if org is None else {"organization_id": org, "role": role}
    return drive.call("POST", "/v1/invitations", token=token, body=body)


def _accept(drive: Any, token: str, username: str) -> Any:
    return drive.call(
        "POST", "/v1/invitations/accept",
        body={"invitation_token": token, "username": username, "display_name": username,
              "password": cc.PASSWORD},
    )  # fmt: skip


def _users_named(drive: Any, username: str) -> int:
    return int(
        drive.cluster.query(
            f"SELECT count(*) FROM app_private.users WHERE username = '{username}';"  # noqa: S608
        )[0]
    )


def test_a_token_is_shown_once_and_stored_hashed(drive: Any, team: dict[str, Any]) -> None:
    minted = _mint(drive, team["tokens"]["admin"], team["org"], "viewer")
    assert minted.status_code == 201, minted.text
    assert minted.headers["cache-control"] == "no-store"
    body = minted.json()
    token = body["invitation_token"]
    assert one_time_tokens.is_wellformed(token)

    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = drive.cluster.query(
        "SELECT token_hash, row_to_json(i)::text FROM app.control_invitations i "  # noqa: S608
        f"WHERE id = '{body['id']}';"
    )[0]
    stored, whole = row.split("|", 1)
    assert stored == digest
    assert token not in whole, "the token itself is stored"

    listed = drive.call(
        "GET", f"/v1/organizations/{team['org']}/invitations", token=team["tokens"]["admin"]
    )
    assert listed.status_code == 200, listed.text
    assert token not in listed.text and digest not in listed.text
    assert body["id"] in listed.text


def test_an_account_invitation_needs_the_registry_administrator_with_a_factor(
    drive: Any, team: dict[str, Any]
) -> None:
    # An owner and an admin of an organisation are not the registry's administrator.
    for who in ("owner", "admin", "outsider"):
        refused = _mint(drive, team["tokens"][who])
        assert (refused.status_code, refused.json()) == (
            403,
            {"error": "authorization_failed"},
        ), who

    # The registry administrator WITHOUT a factor is held at the gate.
    drive.account("inv-registrar-nofactor", admin=True)
    gated = _mint(drive, drive.token("inv-registrar-nofactor"))
    assert (gated.status_code, gated.json()) == (403, {"error": "second_factor_required"})

    served = _mint(drive, team["tokens"]["registrar"])
    assert served.status_code == 201, served.text
    assert (served.json()["organization_id"], served.json()["role"]) == (None, None)

    # And it makes an account and no membership.
    accepted = _accept(drive, served.json()["invitation_token"], "inv-new-account")
    assert accepted.status_code == 200, accepted.text
    assert (accepted.json()["organization_id"], accepted.json()["role"]) == (None, None)
    assert _users_named(drive, "inv-new-account") == 1


def test_a_membership_invitation_is_bounded_by_the_minters_role(
    drive: Any, team: dict[str, Any]
) -> None:
    org = team["org"]
    expected = {
        ("owner", "owner"): 201,
        ("owner", "admin"): 201,
        ("admin", "admin"): 201,
        ("admin", "member"): 201,
        ("admin", "viewer"): 201,
        ("admin", "owner"): 403,
        ("member", "viewer"): 403,
        ("viewer", "viewer"): 403,
        ("outsider", "viewer"): 404,
    }
    observed = {
        (who, role): _mint(drive, team["tokens"][who], org, role).status_code
        for who, role in expected
    }
    assert observed == expected

    # A role without an organisation, or the reverse, is refused by name.
    lopsided = drive.call(
        "POST", "/v1/invitations", token=team["tokens"]["owner"], body={"role": "viewer"}
    )
    assert lopsided.status_code == 422, lopsided.text


def test_acceptance_is_one_transaction(drive: Any, team: dict[str, Any]) -> None:
    # (a) A token that cannot be spent leaves no account behind, though the
    # account would have been created first.
    unknown, _ = one_time_tokens.mint()
    refused = _accept(drive, unknown, "inv-never")
    assert (refused.status_code, refused.json()) == (401, {"error": "invitation_invalid"})
    assert _users_named(drive, "inv-never") == 0

    # (b) A good token whose account cannot be created leaves the token unspent
    # and no membership written.
    token = _mint(drive, team["tokens"]["admin"], team["org"], "member").json()["invitation_token"]
    taken = _accept(drive, token, "inv-viewer")
    assert (taken.status_code, taken.json()) == (409, {"error": "username_taken"})
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert drive.cluster.query(
        "SELECT accepted_at IS NULL FROM app.control_invitations "  # noqa: S608
        f"WHERE token_hash = '{digest}';"
    ) == ["t"]

    # (c) The same token then creates the account, its display row and the
    # membership -- all three, once.
    served = _accept(drive, token, "inv-joined")
    assert served.status_code == 200, served.text
    joined = served.json()
    assert (joined["organization_id"], joined["role"]) == (team["org"], "member")
    assert _users_named(drive, "inv-joined") == 1
    assert drive.cluster.query(
        "SELECT (SELECT count(*) FROM app.control_accounts WHERE user_id = "  # noqa: S608
        f"'{joined['user_id']}') || ',' || (SELECT string_agg(role::text, ',') FROM "
        f"app.control_memberships WHERE user_id = '{joined['user_id']}');"
    ) == ["1,member"]


def test_one_of_two_concurrent_acceptances_succeeds(drive: Any, team: dict[str, Any]) -> None:
    token = _mint(drive, team["tokens"]["admin"], team["org"], "viewer").json()["invitation_token"]
    names = [f"inv-race-{uuid.uuid4().hex[:8]}" for _ in range(2)]
    responses = drive.concurrently(
        *(
            ("POST", "/v1/invitations/accept", None,
             {"invitation_token": token, "username": name, "display_name": name,
              "password": cc.PASSWORD})
            for name in names
        )
    )  # fmt: skip
    assert sorted(response.status_code for response in responses) == [200, 401]
    assert sum(_users_named(drive, name) for name in names) == 1


def test_every_invalid_token_gets_the_same_answer(drive: Any, team: dict[str, Any]) -> None:
    admin = team["tokens"]["admin"]
    org = team["org"]

    used = _mint(drive, admin, org, "viewer").json()["invitation_token"]
    assert _accept(drive, used, "inv-used-once").status_code == 200

    expired = _mint(drive, admin, org, "viewer").json()["invitation_token"]
    digest = hashlib.sha256(expired.encode("utf-8")).hexdigest()
    drive.cluster.query(
        "UPDATE app.control_invitations SET issued_at = now() - interval '3 hours', "  # noqa: S608
        f"expires_at = now() - interval '1 hour' WHERE token_hash = '{digest}';"
    )

    revoked_body = _mint(drive, admin, org, "viewer").json()
    gone = drive.call(
        "DELETE", f"/v1/organizations/{org}/invitations/{revoked_body['id']}", token=admin
    )
    assert gone.status_code == 204, gone.text

    unknown, _ = one_time_tokens.mint()

    answers = {
        name: _accept(drive, token, f"inv-{name}")
        for name, token in (
            ("used", used),
            ("expired", expired),
            ("revoked", revoked_body["invitation_token"]),
            ("unknown", unknown),
            ("malformed", "not-a-token"),
        )
    }
    shapes = {
        name: (r.status_code, r.content, r.headers.get("www-authenticate"))
        for name, r in answers.items()
    }
    assert set(shapes.values()) == {(401, b'{"error":"invitation_invalid"}', "Bearer")}, shapes


def test_a_taken_username_leaves_the_token_unspent(drive: Any, team: dict[str, Any]) -> None:
    token = _mint(drive, team["tokens"]["owner"], team["org"], "viewer").json()["invitation_token"]

    # Taken is answered only AFTER the token validated: an unknown token with a
    # taken name is the invalid-token answer, not a username oracle.
    unknown, _ = one_time_tokens.mint()
    oracle = _accept(drive, unknown, "inv-member")
    assert (oracle.status_code, oracle.json()) == (401, {"error": "invitation_invalid"})

    taken = _accept(drive, token, "inv-member")
    assert (taken.status_code, taken.json()) == (409, {"error": "username_taken"})

    again = _accept(drive, token, "inv-free-name")
    assert again.status_code == 200, again.text
