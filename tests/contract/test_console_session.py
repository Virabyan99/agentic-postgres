"""The console's session, its CSRF rule, the invitation link and the QR, against a real cluster.

Session 43 (ADR 0281, ADR 0282): `CON-SESSION-001`, `CON-CSRF-001`,
`CON-INVITE-001` (the server half) and `CON-FACTOR-001`. The service is the
same `create_app("control")` the container runs (`control_cluster`). Requests
are written the way a browser sends them -- `Cookie`, `Origin` and
`X-Apg-Console` set by the proof, `Set-Cookie` parsed by the proof -- because
what a browser DOES with them is rig 43a's measurement (Chromium: a Strict
cookie rides no cross-site request; a cross-origin `fetch` with the custom
header is never sent past its preflight), not this module's.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from typing import Any

import control_cluster as cc
import pytest

from app import main as main_module
from app import settings as settings_module
from app import totp

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

ORIGIN = cc.console_origin()
FOREIGN = "https://another-site.example"
CONSOLE = {"X-Apg-Console": "1", "Origin": ORIGIN, "Content-Type": "application/json"}
ACCESS = "__Host-apg_access"
REFRESH = "__Host-apg_refresh"


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Any:
    try:
        with cc.control_cluster() as cluster:
            with cc.control_app(cluster, tmp_path_factory.mktemp("console-session")) as driver:
                yield driver
    except RuntimeError as exc:
        pytest.skip(str(exc))


def _set_cookies(response: Any) -> dict[str, dict[str, str]]:
    """Every `Set-Cookie`, as `{name: {"value": ..., <attribute lowercased>: <value>}}`."""
    cookies: dict[str, dict[str, str]] = {}
    for header in response.headers.get_list("set-cookie"):
        first, *attributes = [part.strip() for part in header.split(";")]
        name, _, value = first.partition("=")
        parsed = {"value": value}
        for attribute in attributes:
            key, _, setting = attribute.partition("=")
            parsed[key.lower()] = setting
        assert name not in cookies, f"{name} set twice"
        cookies[name] = parsed
    return cookies


def _console_login(drive: Any, username: str, headers: dict[str, str] | None = None) -> Any:
    body = json.dumps({"username": username, "password": cc.PASSWORD})
    return drive.send("POST", "/v1/sessions", headers=headers or CONSOLE, content=body)


def _console_session(drive: Any, username: str) -> dict[str, str]:
    """`{ACCESS: value, REFRESH: value}` for a fresh console login."""
    response = _console_login(drive, username)
    assert response.status_code == 200, response.text
    return {name: attributes["value"] for name, attributes in _set_cookies(response).items()}


def _cookie_header(**values: str) -> str:
    return "; ".join(f"{name}={value}" for name, value in values.items())


def _with_cookie(session: dict[str, str], **headers: str) -> dict[str, str]:
    return {"Cookie": _cookie_header(**{ACCESS: session[ACCESS]}), **headers}


def _captured(caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    text = "\n".join(
        [record.getMessage() for record in caplog.records] + [captured.out, captured.err]
    )
    assert "apg.http.request" in text, "nothing was captured -- this test would measure nothing"
    return text


# ---------------------------------------------------------------------------
# CON-SESSION-001
# ---------------------------------------------------------------------------


def test_the_console_login_sets_two_host_cookies(drive: Any) -> None:
    drive.account("con-cookies")
    response = _console_login(drive, "con-cookies")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    cookies = _set_cookies(response)
    assert set(cookies) == {ACCESS, REFRESH}, cookies
    for name, attributes in cookies.items():
        assert name.startswith("__Host-")
        assert "httponly" in attributes and "secure" in attributes, (name, attributes)
        assert attributes.get("samesite", "").lower() == "strict", (name, attributes)
        assert attributes.get("path") == "/", (name, attributes)
        assert "domain" not in attributes, (name, attributes)
        assert attributes["value"], name
    assert 1 <= int(cookies[ACCESS]["max-age"]) <= 930, cookies[ACCESS]
    assert int(cookies[REFRESH]["max-age"]) == 30 * 24 * 60 * 60, cookies[REFRESH]


def test_the_console_login_body_holds_no_token(drive: Any) -> None:
    drive.account("con-body")
    response = _console_login(drive, "con-body")
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"expires_at", "token_use"}, response.json()
    for attributes in _set_cookies(response).values():
        assert attributes["value"] not in response.text
    # The control: the same login without the header is the CLI's, tokens in
    # the body and no cookie at all.
    plain = drive.login("con-body")
    assert {"access_token", "refresh_token"} <= set(plain.json())
    assert plain.headers.get_list("set-cookie") == []


def test_refresh_reads_the_cookie(drive: Any) -> None:
    drive.account("con-refresh")
    session = _console_session(drive, "con-refresh")
    headers = {**CONSOLE, "Cookie": _cookie_header(**{REFRESH: session[REFRESH]})}
    refreshed = drive.send("POST", "/v1/sessions/refresh", headers=headers, content="")
    assert refreshed.status_code == 200, refreshed.text
    assert set(refreshed.json()) == {"expires_at", "token_use"}
    successor = _set_cookies(refreshed)
    assert set(successor) == {ACCESS, REFRESH}
    assert successor[REFRESH]["value"] != session[REFRESH]
    # Single use, as it always was: the spent cookie is refused.
    again = drive.send("POST", "/v1/sessions/refresh", headers=headers, content="")
    assert again.status_code == 401, again.text


def test_logout_clears_both(drive: Any) -> None:
    drive.account("con-logout")
    session = _console_session(drive, "con-logout")
    headers = {**CONSOLE, "Cookie": _cookie_header(**{REFRESH: session[REFRESH]})}
    ended = drive.send("DELETE", "/v1/sessions/current", headers=headers, content="")
    assert ended.status_code == 204, ended.text
    cleared = _set_cookies(ended)
    assert set(cleared) == {ACCESS, REFRESH}, cleared
    for name, attributes in cleared.items():
        assert attributes["max-age"] == "0", (name, attributes)
        assert "secure" in attributes and attributes.get("path") == "/", (name, attributes)
    refused = drive.send("POST", "/v1/sessions/refresh", headers=headers, content="")
    assert refused.status_code == 401, "the family outlived its logout"


def test_a_bearer_request_ignores_cookies(drive: Any) -> None:
    """`Authorization` wins: the CLI's path is untouched by a cookie, good or bad."""
    drive.account("con-bearer")
    token = drive.token("con-bearer")
    session = _console_session(drive, "con-bearer")
    garbage = {ACCESS: "not-a-token"}
    served = drive.send(
        "GET", "/v1/me",
        headers={"Authorization": f"Bearer {token}", "Cookie": _cookie_header(**garbage),
                 "X-Apg-Console": "1", "Origin": ORIGIN},
    )  # fmt: skip
    assert served.status_code == 200, served.text
    refused = drive.send(
        "GET", "/v1/me",
        headers={"Authorization": "Bearer not-a-token", **_with_cookie(session),
                 "X-Apg-Console": "1", "Origin": ORIGIN},
    )  # fmt: skip
    assert refused.status_code == 401, "a cookie stood in for a bad bearer"


def test_a_key_in_a_cookie_is_refused(drive: Any) -> None:
    """A real management key: by bearer on `/v1/me` it is `human_session_required`
    (the key path); as the console's cookie it is no credential at all."""
    owner = drive.account("con-key-owner")
    seed = drive.enable_factor(owner)
    org = drive.organization(owner)
    token = drive.token("con-key-owner", seed)
    minted = drive.call(
        "POST", f"/v1/organizations/{org}/keys", token=token,
        body={"name": "k", "scopes": ["projects:read"]},
    )  # fmt: skip
    assert minted.status_code == 201, minted.text
    key = minted.json()["key"]
    assert key.startswith("apg_")

    by_bearer = drive.send("GET", "/v1/me", headers={"Authorization": f"Bearer {key}"})
    assert (by_bearer.status_code, by_bearer.json()) == (
        403, {"error": "human_session_required"}
    )  # fmt: skip
    by_cookie = drive.send(
        "GET", "/v1/me",
        headers={"Cookie": _cookie_header(**{ACCESS: key}), "X-Apg-Console": "1"},
    )  # fmt: skip
    assert (by_cookie.status_code, by_cookie.json()) == (
        401, {"error": "authentication_failed"}
    )  # fmt: skip


# ---------------------------------------------------------------------------
# CON-CSRF-001
# ---------------------------------------------------------------------------


def test_a_cookie_without_the_header_is_unauthenticated(drive: Any) -> None:
    drive.account("con-header")
    session = _console_session(drive, "con-header")
    without = drive.send("GET", "/v1/me", headers=_with_cookie(session, Origin=ORIGIN))
    assert without.status_code == 401, without.text
    # The control: the same cookie with the header is the person.
    served = drive.send("GET", "/v1/me", headers=_with_cookie(session, **{"X-Apg-Console": "1"}))
    assert served.status_code == 200, served.text
    assert served.json()["username"] == "con-header"


def test_a_write_from_another_origin_is_refused(drive: Any) -> None:
    drive.account("con-origin")
    session = _console_session(drive, "con-origin")
    foreign = drive.send(
        "POST", "/v1/me/totp",
        headers=_with_cookie(session, **{"X-Apg-Console": "1", "Origin": FOREIGN}),
    )  # fmt: skip
    assert foreign.status_code == 401, foreign.text
    login = _console_login(drive, "con-origin", {**CONSOLE, "Origin": FOREIGN})
    assert login.status_code == 401 and login.headers.get_list("set-cookie") == []
    # The control: the console's own origin writes.
    own = drive.send(
        "POST", "/v1/me/totp",
        headers=_with_cookie(session, **{"X-Apg-Console": "1", "Origin": ORIGIN}),
    )  # fmt: skip
    assert own.status_code == 201, own.text


def test_a_write_without_an_origin_is_refused(drive: Any) -> None:
    drive.account("con-no-origin")
    session = _console_session(drive, "con-no-origin")
    write = drive.send(
        "POST", "/v1/me/totp", headers=_with_cookie(session, **{"X-Apg-Console": "1"})
    )
    assert write.status_code == 401, write.text
    # A read needs no Origin (a browser sends none on a same-origin GET).
    read = drive.send("GET", "/v1/me", headers=_with_cookie(session, **{"X-Apg-Console": "1"}))
    assert read.status_code == 200, read.text


def test_no_cors_header_is_answered(drive: Any) -> None:
    """The custom header makes a cross-origin request preflighted; nothing
    answers the preflight, and nothing answers CORS on a real request either."""
    preflight = drive.send(
        "OPTIONS", "/v1/sessions",
        headers={"Origin": FOREIGN, "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "x-apg-console, content-type"},
    )  # fmt: skip
    drive.account("con-cors")
    login = _console_login(drive, "con-cors")
    for response in (preflight, login):
        allowed = [name for name in response.headers if name.lower().startswith("access-control-")]
        assert allowed == [], allowed
    assert preflight.status_code >= 400, preflight.status_code


def test_no_line_holds_a_cookie_value(
    drive: Any, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    drive.account("con-quiet")
    caplog.set_level(logging.DEBUG)
    session = _console_session(drive, "con-quiet")
    drive.send("GET", "/v1/me", headers=_with_cookie(session, **{"X-Apg-Console": "1"}))
    headers = {**CONSOLE, "Cookie": _cookie_header(**{REFRESH: session[REFRESH]})}
    drive.send("POST", "/v1/sessions/refresh", headers=headers, content="")
    text = _captured(caplog, capsys)
    leaked = [name for name, value in session.items() if value in text]
    assert not leaked, f"a log line carries {leaked}"


# ---------------------------------------------------------------------------
# CON-INVITE-001 (the server half)
# ---------------------------------------------------------------------------


def _owner_with_org(drive: Any, name: str) -> tuple[str, str]:
    owner = drive.account(name)
    seed = drive.enable_factor(owner)
    return drive.organization(owner), drive.token(name, seed)


def test_the_mint_answers_the_accept_url(drive: Any) -> None:
    org, token = _owner_with_org(drive, "con-inviter")
    minted = drive.call(
        "POST", "/v1/invitations", token=token, body={"organization_id": org, "role": "member"}
    )
    assert minted.status_code == 201, minted.text
    body = minted.json()
    invitation = body["invitation_token"]
    assert body["accept_url"] == f"{ORIGIN}/accept#{invitation}"
    link = urllib.parse.urlsplit(body["accept_url"])
    assert (link.scheme, link.path, link.query, link.fragment) == (
        "https", "/accept", "", invitation
    )  # fmt: skip


def test_no_line_holds_the_invitation_token(
    drive: Any, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    org, token = _owner_with_org(drive, "con-invite-quiet")
    caplog.set_level(logging.DEBUG)
    body = drive.call(
        "POST", "/v1/invitations", token=token, body={"organization_id": org, "role": "viewer"}
    ).json()
    accepted = drive.call(
        "POST", "/v1/invitations/accept",
        body={"invitation_token": body["invitation_token"], "username": "con-invitee",
              "display_name": "con-invitee", "password": cc.PASSWORD},
    )  # fmt: skip
    assert accepted.status_code == 200, accepted.text
    text = _captured(caplog, capsys)
    assert body["invitation_token"] not in text, "a log line carries the invitation token"


# ---------------------------------------------------------------------------
# CON-FACTOR-001
# ---------------------------------------------------------------------------


def _decoded(data_uri: str) -> str:
    prefix = "data:image/svg+xml;charset=utf-8,"
    assert data_uri.startswith(prefix), data_uri[:60]
    return urllib.parse.unquote(data_uri[len(prefix) :])


def test_the_enrolment_answer_carries_the_qr(drive: Any) -> None:
    drive.account("con-qr")
    session = _console_session(drive, "con-qr")
    console_write = {"X-Apg-Console": "1", "Origin": ORIGIN}
    begun = drive.send("POST", "/v1/me/totp", headers=_with_cookie(session, **console_write))
    assert begun.status_code == 201, begun.text
    enrolment = begun.json()
    assert set(enrolment) == {"secret", "otpauth_uri", "otpauth_qr"}
    # The image IS the URI: drawn from it, deterministically.
    assert enrolment["otpauth_qr"] == totp.qr_data_uri(enrolment["otpauth_uri"])
    assert _decoded(enrolment["otpauth_qr"]).startswith("<svg")


def test_the_qr_references_nothing() -> None:
    """No script, no link, no URL but the SVG namespace -- and its own white
    background, without which a scanner reads nothing on a dark page (D2682)."""
    uri = totp.provisioning_uri("con-reader", bytes(range(20)))
    svg = _decoded(totp.qr_data_uri(uri))
    lowered = svg.lower()
    assert "<script" not in lowered and "href" not in lowered and "url(" not in lowered
    assert lowered.count("http") == lowered.count("http://www.w3.org/2000/svg") == 1
    assert "fill='#fff'" in svg, "the QR carries no light background of its own"


# ---------------------------------------------------------------------------
# The origin both rules read
# ---------------------------------------------------------------------------


def test_a_control_process_without_the_origin_does_not_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compared byte for byte with `Origin` and the base of every link, so a value
    that could never equal a browser's `Origin` is refused at start, never served."""
    assert settings_module.load_console_origin({"APG_CONSOLE_ORIGIN": ORIGIN}) == ORIGIN
    for refused in ("", "http://control.example.test", "https://control.example.test/",
                    "https://control.example.test/console", "control.example.test"):  # fmt: skip
        with pytest.raises(settings_module.MissingSetting, match="APG_CONSOLE_ORIGIN"):
            settings_module.load_console_origin({"APG_CONSOLE_ORIGIN": refused})
    # The start itself: the lifespan reads it first, so a control container
    # without it fails on THIS name. Building the app reads nothing (the
    # snapshot is `create_app("control").openapi()` with no environment).
    monkeypatch.delenv("APG_CONSOLE_ORIGIN", raising=False)
    application = main_module.create_app("control")
    assert "/v1/sessions" in main_module.route_paths(application)
    starting = application.router.lifespan_context(application)
    with pytest.raises(settings_module.MissingSetting, match="APG_CONSOLE_ORIGIN"):
        asyncio.run(starting.__aenter__())
