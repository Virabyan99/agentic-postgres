"""The control mode's session plane and second factor, against a real cluster.

CTL-TOTP-001's session half (ADR 0252, D2050, D2080): the code is required at
login once a factor is enabled, and refused when wrong or replayed; confirming
a factor ends every session; an owner without a factor reaches only
enrolment; neither a seed nor a code reaches a log line. The service is the
same `create_app("control")` the container runs, over the control set applied
to the locked image (`control_cluster`).
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

import control_cluster as cc
import pytest

from app import totp

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Any:
    try:
        with cc.control_cluster() as cluster:
            with cc.control_app(cluster, tmp_path_factory.mktemp("control-sessions")) as driver:
                yield driver
    except RuntimeError as exc:
        pytest.skip(str(exc))


def _seed_of(enrolment: dict[str, Any]) -> bytes:
    secret = enrolment["secret"]
    return base64.b32decode(secret + "=" * (-len(secret) % 8))


def _enrol(drive: Any, token: str) -> bytes:
    """Begin and confirm through the API; returns the seed. The confirming
    code is the CURRENT step's, so the next login uses the next step's."""
    begun = drive.call("POST", "/v1/me/totp", token=token)
    assert begun.status_code == 201, begun.text
    assert begun.headers["cache-control"] == "no-store"
    seed = _seed_of(begun.json())
    confirmed = drive.call(
        "POST", "/v1/me/totp/confirm", token=token,
        body={"totp_code": totp.totp(seed, int(time.time()))},
    )  # fmt: skip
    assert confirmed.status_code == 200, confirmed.text
    return seed


def test_login_requires_the_code_once_enabled(drive: Any) -> None:
    drive.account("s37-login")
    # Control: no factor yet, so the password alone is served.
    token = drive.token("s37-login")
    seed = _enrol(drive, token)

    without = drive.login("s37-login")
    assert (without.status_code, without.json()) == (401, {"error": "second_factor_required"})
    assert without.headers["www-authenticate"] == "Bearer"

    right = totp.totp(seed, int(time.time()) + totp.STEP_SECONDS)
    wrong = "000000" if right != "000000" else "111111"
    refused = drive.call(
        "POST", "/v1/sessions",
        body={"username": "s37-login", "password": cc.PASSWORD, "totp_code": wrong},
    )  # fmt: skip
    assert (refused.status_code, refused.json()) == (401, {"error": "second_factor_invalid"})

    served = drive.call(
        "POST", "/v1/sessions",
        body={"username": "s37-login", "password": cc.PASSWORD, "totp_code": right},
    )  # fmt: skip
    assert served.status_code == 200, served.text
    assert served.headers["cache-control"] == "no-store"

    replayed = drive.call(
        "POST", "/v1/sessions",
        body={"username": "s37-login", "password": cc.PASSWORD, "totp_code": right},
    )  # fmt: skip
    assert (replayed.status_code, replayed.json()) == (401, {"error": "second_factor_invalid"})

    # The password still comes first: a wrong one is the release's one answer,
    # whatever the code.
    no_password = drive.call(
        "POST", "/v1/sessions",
        body={"username": "s37-login", "password": "not-the-password", "totp_code": right},
    )  # fmt: skip
    assert (no_password.status_code, no_password.json()) == (
        401,
        {"error": "authentication_failed"},
    )


def test_confirming_a_factor_revokes_every_session(drive: Any) -> None:
    drive.account("s37-revoke")
    first = drive.login("s37-revoke").json()
    second = drive.login("s37-revoke").json()

    seed = _enrol(drive, first["access_token"])

    for session in (first, second):
        refreshed = drive.call(
            "POST", "/v1/sessions/refresh", body={"refresh_token": session["refresh_token"]}
        )
        assert (refreshed.status_code, refreshed.json()) == (
            401,
            {"error": "authentication_failed"},
        )

    # Control: a session opened AFTER enrolment, with the code, refreshes.
    after = drive.login("s37-revoke", seed, offset=1).json()
    renewed = drive.call(
        "POST", "/v1/sessions/refresh", body={"refresh_token": after["refresh_token"]}
    )
    assert renewed.status_code == 200, renewed.text


def test_an_owner_without_a_factor_reaches_only_enrolment(drive: Any) -> None:
    owner = drive.account("s37-gate")
    org = drive.organization(owner)
    token = drive.token("s37-gate")

    me = drive.call("GET", "/v1/me", token=token)
    assert me.status_code == 200, me.text
    assert me.json()["second_factor"] == {"enabled": False, "required": True}

    for method, path, body in (
        ("GET", "/v1/organizations", None),
        ("POST", "/v1/organizations", {"name": "another"}),
        ("GET", f"/v1/organizations/{org}", None),
        ("GET", f"/v1/organizations/{org}/members", None),
        ("GET", f"/v1/organizations/{org}/invitations", None),
        ("POST", "/v1/invitations", {"organization_id": org, "role": "viewer"}),
    ):
        refused = drive.call(method, path, token=token, body=body)
        assert (refused.status_code, refused.json()) == (
            403,
            {"error": "second_factor_required"},
        ), (method, path)

    # Enrolment is reachable -- and once it is done, so is everything else.
    seed = _enrol(drive, token)
    enrolled = drive.token("s37-gate", seed, offset=1)
    listed = drive.call("GET", "/v1/organizations", token=enrolled)
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["organizations"]] == [org]

    # Control: a member without a factor is not gated at all.
    member = drive.account("s37-gate-member")
    drive.member(org, member, "member")
    plain = drive.call("GET", f"/v1/organizations/{org}", token=drive.token("s37-gate-member"))
    assert plain.status_code == 200, plain.text


def test_no_seed_reaches_a_log_line(
    drive: Any, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    drive.account("s37-quiet")
    caplog.set_level(logging.DEBUG)
    token = drive.token("s37-quiet")

    begun = drive.call("POST", "/v1/me/totp", token=token).json()
    seed = _seed_of(begun)
    confirming = totp.totp(seed, int(time.time()))
    confirmed = drive.call(
        "POST", "/v1/me/totp/confirm", token=token, body={"totp_code": confirming}
    )
    assert confirmed.status_code == 200, confirmed.text
    logging_in = totp.totp(seed, int(time.time()) + totp.STEP_SECONDS)
    served = drive.call(
        "POST", "/v1/sessions",
        body={"username": "s37-quiet", "password": cc.PASSWORD, "totp_code": logging_in},
    )  # fmt: skip
    assert served.status_code == 200, served.text

    planted = {
        "base32 secret": begun["secret"],
        "seed hex": seed.hex(),
        "enrolment uri": begun["otpauth_uri"],
        "confirming code": confirming,
        "login code": logging_in,
    }
    captured = capsys.readouterr()
    text = "\n".join(
        [record.getMessage() for record in caplog.records] + [captured.out, captured.err]
    )
    # The capture itself is read: the request log wrote a line for each call.
    assert "apg.http.request" in text, "nothing was captured -- this test would measure nothing"
    leaked = [name for name, value in planted.items() if value in text]
    assert not leaked, f"a log line carries the {leaked}"
