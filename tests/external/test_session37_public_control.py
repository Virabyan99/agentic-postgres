"""Session 37's customer proofs: the control plane through its public door.

The first EXTERNAL claims that are a customer's (`control_invitations_live`,
`control_totp_live`, `control_keys_live`). Run from the workstation, never the
host, and **every request goes to `routes.control`** of the control project's
deployed document (`APG_CONTROL_OUTPUTS`) over https -- except the two a key's
REFUSAL is measured at, alpha's `routes.app` and `routes.rest`
(`APG_PROJECT_A_OUTPUTS`). D2058: the gate's external mode still needs
`--ssh-destination` for Session 4's proofs, so instead of an unset variable
these proofs prove they never use the SSH path -- statically
(`test_control_boundary.py::test_session37_customer_proofs_reach_only_the_public_endpoint`
reads this file) and at run time (every request through `Recorder`, whose
hosts each proof asserts).

The probe owner (`APG_CONTROL_PROBE_FILE`, 0600) was enrolled through the
product's own commands by the trip (D2125): a password file and a TOTP seed,
an organisation it owns. **A TOTP step is accepted once**, so every code here
comes from `_fresh_code`, which waits for a step after the last one used.

**Each proof creates its own `probe-s37-<8 hex>` accounts and removes their
memberships at the end** (D2065): accounts are never deleted in Session 37,
and the membership is the authority -- without it an account reaches nothing
but `/v1/me`.
"""

from __future__ import annotations

import json
import os
import secrets
import ssl
import stat
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment(
        "APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE", "APG_PROJECT_A_OUTPUTS"
    ),
]

TIMEOUT = 30


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class Recorder:
    """Every request a proof makes, and where it went. Never follows a redirect:
    a bearer must not be carried to a host the proof did not choose."""

    def __init__(self) -> None:
        self.opener = urllib.request.build_opener(
            _NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context())
        )
        self.seen: list[tuple[str, str]] = []

    def send(
        self, method: str, url: str, body: Any = None, bearer: str | None = None
    ) -> tuple[int, bytes]:
        parts = urlsplit(url)
        self.seen.append((parts.scheme, parts.hostname or ""))
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)  # noqa: S310
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if bearer is not None:
            request.add_header("Authorization", f"Bearer {bearer}")
        try:
            with self.opener.open(request, timeout=TIMEOUT) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def json(
        self, method: str, url: str, body: Any = None, bearer: str | None = None
    ) -> tuple[int, Any]:
        status, raw = self.send(method, url, body, bearer)
        try:
            return status, json.loads(raw) if raw else {}
        except ValueError:
            return status, {"raw": raw[:200].decode("utf-8", "replace")}

    def hosts(self) -> set[tuple[str, str]]:
        return set(self.seen)


@pytest.fixture(scope="module")
def control() -> dict[str, Any]:
    return json.loads(Path(os.environ["APG_CONTROL_OUTPUTS"]).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def project_a() -> dict[str, Any]:
    return json.loads(Path(os.environ["APG_PROJECT_A_OUTPUTS"]).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def endpoint(control: dict[str, Any]) -> str:
    route = (control.get("routes") or {}).get("control") or {}
    if route.get("status") != "ready" or not route.get("url"):
        pytest.fail(f"the control project publishes no ready control route: {route}")
    assert route["url"].startswith("https://"), route["url"]
    return route["url"].rstrip("/")


@pytest.fixture(scope="module")
def probe(endpoint: str) -> dict[str, Any]:
    path = Path(os.environ["APG_CONTROL_PROBE_FILE"])
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600, f"{path} is {oct(mode)}; the probe owner's file is 0600"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["endpoint"].rstrip("/") == endpoint, (document["endpoint"], endpoint)
    password_file = Path(document["password_file"])
    assert stat.S_IMODE(password_file.stat().st_mode) == 0o600, password_file
    return {**document, "password": password_file.read_text(encoding="utf-8").strip("\n")}


_LAST_STEP = [0]


def _fresh_code(seed_text: str) -> str:
    """A code for a step after the last one this module used (a step is
    accepted once; the server refuses a step at or below the last accepted)."""
    import base64

    from app import totp

    seed = base64.b32decode(seed_text + "=" * (-len(seed_text) % 8))
    while totp.step_of(int(time.time())) <= _LAST_STEP[0]:
        time.sleep(0.5)
    now = int(time.time())
    _LAST_STEP[0] = totp.step_of(now)
    return totp.totp(seed, now)


@pytest.fixture
def recorder() -> Recorder:
    """One per proof, so each proof's hosts are its own."""
    return Recorder()


@pytest.fixture(scope="module")
def owner(endpoint: str, probe: dict[str, Any]) -> Iterator[str]:
    """The probe owner's access token for the module; the session ended after.
    Its own recorder, held to the control host like every proof's."""
    own = Recorder()
    status, body = own.json("POST", f"{endpoint}/sessions", {
        "username": probe["username"], "password": probe["password"],
        "totp_code": _fresh_code(probe["totp_seed"]),
    })  # fmt: skip
    assert status == 200, (status, body.get("error"))
    yield body["access_token"]
    own.send("DELETE", f"{endpoint}/sessions/current",
             {"refresh_token": body["refresh_token"]}, body["access_token"])  # fmt: skip
    _only_control(own, endpoint)


def _username() -> str:
    return f"probe-s37-{secrets.token_hex(4)}"


def _invite(recorder: Recorder, endpoint: str, owner: str, organization: str, role: str) -> str:
    status, body = recorder.json(
        "POST", f"{endpoint}/invitations", {"organization_id": organization, "role": role}, owner
    )
    assert status == 201, (status, body.get("error"))
    return body["invitation_token"]


def _accept(
    recorder: Recorder, endpoint: str, token: str, username: str, password: str
) -> tuple[int, bytes]:
    return recorder.send("POST", f"{endpoint}/invitations/accept", {
        "invitation_token": token, "username": username, "display_name": username,
        "password": password,
    })  # fmt: skip


def _member(recorder: Recorder, endpoint: str, owner: str, organization: str) -> dict[str, str]:
    """A new `probe-s37-*` member of the probe organisation, logged in."""
    username, password = _username(), secrets.token_urlsafe(24)
    token = _invite(recorder, endpoint, owner, organization, "member")
    status, raw = _accept(recorder, endpoint, token, username, password)
    assert status == 200, (status, raw[:200])
    user = json.loads(raw)["user_id"]
    status, body = recorder.json(
        "POST", f"{endpoint}/sessions", {"username": username, "password": password}
    )
    assert status == 200, (status, body.get("error"))
    return {"user": user, "username": username, "token": body["access_token"]}


def _remove(recorder: Recorder, endpoint: str, owner: str, organization: str, user: str) -> None:
    status, _ = recorder.send(
        "DELETE", f"{endpoint}/organizations/{organization}/members/{user}", None, owner
    )
    assert status == 204, f"the membership of {user} was not removed ({status})"


def _key(recorder: Recorder, endpoint: str, member: dict[str, str], organization: str) -> str:
    status, body = recorder.json(
        "POST", f"{endpoint}/organizations/{organization}/keys",
        {"name": "probe-s37", "scopes": ["organizations:read", "projects:read"]}, member["token"],
    )  # fmt: skip
    assert status == 201, (status, body.get("error"))
    return body["key"]


def _only_control(recorder: Recorder, endpoint: str) -> None:
    allowed = {("https", urlsplit(endpoint).hostname or "")}
    assert recorder.hosts() <= allowed, sorted(recorder.hosts() - allowed)


def test_an_invitation_is_accepted_once(
    recorder: Recorder, endpoint: str, owner: str, probe: dict[str, Any]
) -> None:
    """CTL-INV-002: the probe owner mints a membership invitation; it is
    accepted once; a second acceptance of the same token and an unknown token
    get the same answer, byte for byte."""
    from app import one_time_tokens

    organization = probe["organization_id"]
    token = _invite(recorder, endpoint, owner, organization, "member")
    username = _username()
    status, raw = _accept(recorder, endpoint, token, username, secrets.token_urlsafe(24))
    assert status == 200, (status, raw[:200])
    user = json.loads(raw)["user_id"]
    try:
        again = _accept(recorder, endpoint, token, _username(), secrets.token_urlsafe(24))
        unknown_token, _ = one_time_tokens.mint()
        unknown = _accept(recorder, endpoint, unknown_token, _username(), secrets.token_urlsafe(24))
        assert again == unknown, (again, unknown)
        assert again[0] == 401, again
    finally:
        _remove(recorder, endpoint, owner, organization, user)
    _only_control(recorder, endpoint)


def test_login_enforces_the_second_factor(
    recorder: Recorder, endpoint: str, probe: dict[str, Any]
) -> None:
    """CTL-TOTP-002: without the code, a wrong code, and a replayed code are
    refused; the current code is served (its session ended at once)."""
    url = f"{endpoint}/sessions"
    credentials = {"username": probe["username"], "password": probe["password"]}
    status, body = recorder.json("POST", url, credentials)
    assert (status, body.get("error")) == (401, "second_factor_required"), (status, body)

    code = _fresh_code(probe["totp_seed"])
    wrong = f"{(int(code) + 500_000) % 1_000_000:06d}"
    status, body = recorder.json("POST", url, {**credentials, "totp_code": wrong})
    assert (status, body.get("error")) == (401, "second_factor_invalid"), (status, body)

    status, served = recorder.json("POST", url, {**credentials, "totp_code": code})
    assert status == 200, (status, served.get("error"))
    recorder.send("DELETE", f"{endpoint}/sessions/current",
                  {"refresh_token": served["refresh_token"]}, served["access_token"])  # fmt: skip

    status, body = recorder.json("POST", url, {**credentials, "totp_code": code})
    assert (status, body.get("error")) == (401, "second_factor_invalid"), (status, body)
    _only_control(recorder, endpoint)


def test_a_key_lists_projects_and_opens_no_project(
    recorder: Recorder,
    endpoint: str,
    owner: str,
    probe: dict[str, Any],
    project_a: dict[str, Any],
    tmp_path: Path,
) -> None:
    """KEY-USE-001, the first half: a member's key lists, through `bin/project.sh
    list`, exactly what the owner's session lists for the organisation -- and
    none of another organisation's projects (alpha is adopted into the
    operator's, not the probe's); the key gets 404 for alpha's record, and is
    refused (401) by alpha's own application and REST routes."""
    organization = probe["organization_id"]
    app_route = project_a["routes"]["app"]["url"].rstrip("/")
    rest_route = project_a["routes"]["rest"]["url"].rstrip("/")
    member = _member(recorder, endpoint, owner, organization)
    try:
        key = _key(recorder, endpoint, member, organization)
        status, body = recorder.json(
            "GET", f"{endpoint}/projects?organization={organization}", None, owner
        )
        assert status == 200, status
        expected = sorted(p["key"] for p in body["projects"])

        key_file = tmp_path / "key"
        key_file.write_text(key + "\n", encoding="utf-8")
        key_file.chmod(0o600)
        environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path),
                       "LANG": "C.UTF-8", "XDG_CONFIG_HOME": str(tmp_path / "config")}  # fmt: skip

        def command(name: str, *argv: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [str(REPO_ROOT / "bin" / f"{name}.sh"), *argv], stdin=subprocess.DEVNULL,
                capture_output=True, text=True, env=environment, timeout=120, check=False,
            )  # fmt: skip

        logged = command("login", "key", "--endpoint", endpoint, "--key-file", str(key_file))
        assert logged.returncode == 0, logged.stderr[-300:]
        listed = command("project", "list", "--json")
        assert listed.returncode == 0, listed.stderr[-300:]
        assert sorted(p["key"] for p in json.loads(listed.stdout)) == expected
        alpha = project_a["project"]["key"]
        assert alpha not in expected, f"{alpha} is in the probe organisation"

        status, _ = recorder.send("GET", f"{endpoint}/projects/{alpha}", None, key)
        assert status == 404, status
        status, _ = recorder.send("GET", f"{app_route}/auth/me", None, key)
        assert status == 401, f"alpha's application answered a management key with {status}"
        status, _ = recorder.send("GET", f"{rest_route}/", None, key)
        assert status == 401, f"alpha's REST route answered a management key with {status}"
    finally:
        _remove(recorder, endpoint, owner, organization, member["user"])
    allowed = {("https", urlsplit(u).hostname or "") for u in (endpoint, app_route, rest_route)}
    assert recorder.hosts() <= allowed, sorted(recorder.hosts() - allowed)


def test_a_departed_members_key_stops(
    recorder: Recorder, endpoint: str, owner: str, probe: dict[str, Any]
) -> None:
    """KEY-USE-001, the second half: two members, a key each; the owner removes
    the first; the first key is refused on its next request while the
    sibling's is served."""
    organization = probe["organization_id"]
    leaver = _member(recorder, endpoint, owner, organization)
    sibling = _member(recorder, endpoint, owner, organization)
    removed = False
    try:
        leaving_key = _key(recorder, endpoint, leaver, organization)
        sibling_key = _key(recorder, endpoint, sibling, organization)
        listing = f"{endpoint}/projects?organization={organization}"
        assert recorder.send("GET", listing, None, leaving_key)[0] == 200
        _remove(recorder, endpoint, owner, organization, leaver["user"])
        removed = True
        status, raw = recorder.send("GET", listing, None, leaving_key)
        assert status == 401, (status, raw[:200])
        assert recorder.send("GET", listing, None, sibling_key)[0] == 200
    finally:
        if not removed:
            _remove(recorder, endpoint, owner, organization, leaver["user"])
        _remove(recorder, endpoint, owner, organization, sibling["user"])
    _only_control(recorder, endpoint)
