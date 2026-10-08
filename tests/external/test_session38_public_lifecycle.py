"""Session 38's customer proofs: a managed project's life, read back through the public doors.

The claims `lifecycle_operations_live` (LIFE-LIVE-001) and
`lifecycle_project_door_live` (LIFE-LIVE-002). Run from the workstation,
never the host, AFTER the lifecycle (Run 12, D2175): `s38-lifecycle.py` drove
one project through `/v1` with the product's own commands -- created, claimed,
slept, woken, resized twice, exported twice, deleted, and a second creation
refused -- and wrote `APG_LIFECYCLE_RECORD_FILE` (0600): the operations' ids,
the status codes and seconds it observed, the slot's key and `routes.app`, and
the commit the slot was deployed at. Never a password, a token or a URL that
authorises anything.

**These proofs read that record and ask the deployment again.** Every
operation it names is re-read through `routes.control` of the control
project's document (`APG_CONTROL_OUTPUTS`) as the probe owner
(`APG_CONTROL_PROBE_FILE`), and the slot's own address is asked once more --
the record says what the customer saw, the deployment says it still holds. A
record from another commit than the control project's deployed one is refused
(§7), and so is a record that stopped before its end.

D2174: **every request goes to `routes.control` or to the slot's recorded
`routes.app`**, statically (`test_control_boundary.py`'s
`test_session38_customer_proofs_reach_only_the_public_endpoint` reads this
file) and at run time (every request through `Recorder`, whose
hosts each proof asserts). The SSH path the gate's external mode still needs
for Session 4 is never used here. **None of these six proofs has ever
executed.**
"""

from __future__ import annotations

import json
import os
import ssl
import stat
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment(
        "APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE", "APG_LIFECYCLE_RECORD_FILE"
    ),
]

TIMEOUT = 30

#: What the lifecycle ran, in the order it ran it (D2175): each operation's type
#: and the terminal status the customer read.
LIFECYCLE = (
    ("project.create", "succeeded"),
    ("project.sleep", "succeeded"),
    ("project.wake", "succeeded"),
    ("project.resize", "succeeded"),
    ("project.resize", "failed"),
    ("project.export", "succeeded"),
    ("project.export", "succeeded"),
    ("project.delete", "succeeded"),
)

#: The edge's answer for a host or path no router serves (rig 38b: 19 bytes).
EDGE_404 = b"404 page not found"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class Recorder:
    """Every request a proof makes, and where it went. Never follows a redirect."""

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
def endpoint(control: dict[str, Any]) -> str:
    route = (control.get("routes") or {}).get("control") or {}
    if route.get("status") != "ready" or not route.get("url"):
        pytest.fail(f"the control project publishes no ready control route: {route}")
    assert route["url"].startswith("https://"), route["url"]
    return route["url"].rstrip("/")


@pytest.fixture(scope="module")
def probe(endpoint: str) -> dict[str, Any]:
    path = Path(os.environ["APG_CONTROL_PROBE_FILE"])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600, f"{path} is not 0600"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["endpoint"].rstrip("/") == endpoint, (document["endpoint"], endpoint)
    password_file = Path(document["password_file"])
    assert stat.S_IMODE(password_file.stat().st_mode) == 0o600, password_file
    return {**document, "password": password_file.read_text(encoding="utf-8").strip("\n")}


@pytest.fixture(scope="module")
def record(control: dict[str, Any], endpoint: str, probe: dict[str, Any]) -> dict[str, Any]:
    """The lifecycle's record: private, finished, the probe owner's, at the
    control project's endpoint, and about the commit that is deployed (§7)."""
    path = Path(os.environ["APG_LIFECYCLE_RECORD_FILE"])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600, f"{path} is not 0600"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document.get("session") == 38, document.get("session")
    assert document.get("finished") is True and "stopped" not in document, (
        f"the lifecycle did not run to its end: {document.get('stopped')}"
    )
    assert document["endpoint"].rstrip("/") == endpoint, document["endpoint"]
    assert document["username"] == probe["username"], document["username"]
    assert document.get("source_commit") == control["source_commit"], (
        f"the record's slot was deployed at {document.get('source_commit')}, the control "
        f"project is at {control['source_commit']}: a record from another release"
    )
    assert str(document.get("app_route", "")).startswith("https://"), document.get("app_route")
    return document


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


_LAST_STEP = [0]


def _fresh_code(seed_text: str) -> str:
    """A TOTP code for a step after the last one this module used."""
    import base64

    from app import totp

    seed = base64.b32decode(seed_text + "=" * (-len(seed_text) % 8))
    while totp.step_of(int(time.time())) <= _LAST_STEP[0]:
        time.sleep(0.5)
    now = int(time.time())
    _LAST_STEP[0] = totp.step_of(now)
    return totp.totp(seed, now)


@pytest.fixture(scope="module")
def owner(endpoint: str, probe: dict[str, Any]) -> Iterator[str]:
    """The probe owner's access token for the module; the session ended after."""
    own = Recorder()
    status, body = own.json("POST", f"{endpoint}/sessions", {
        "username": probe["username"], "password": probe["password"],
        "totp_code": _fresh_code(probe["totp_seed"]),
    })  # fmt: skip
    assert status == 200, (status, body.get("error"))
    yield body["access_token"]
    own.send("DELETE", f"{endpoint}/sessions/current",
             {"refresh_token": body["refresh_token"]}, body["access_token"])  # fmt: skip
    _only(own, endpoint)


def _only(recorder: Recorder, *urls: str) -> None:
    allowed = {("https", urlsplit(url).hostname or "") for url in urls}
    assert recorder.hosts() <= allowed, sorted(recorder.hosts() - allowed)


def _read_back(
    recorder: Recorder, endpoint: str, owner: str, record: dict[str, Any]
) -> list[dict[str, Any]]:
    """Every operation the record names, as `/v1` answers it now, in the order
    the operations were created."""
    rows = []
    for kept in record["operations"]:
        status, row = recorder.json("GET", f"{endpoint}/operations/{kept['id']}", None, owner)
        assert status == 200, (kept["id"], status, row.get("error"))
        rows.append(row)
    return sorted(rows, key=lambda row: row["created_at"])


def test_the_operations_read_as_the_lifecycle_ran(
    recorder: Recorder, endpoint: str, owner: str, record: dict[str, Any]
) -> None:
    """LIFE-LIVE-001: the eight operations the record names read back through
    `/v1`, in creation order, as the lifecycle ran -- create, sleep, wake and
    resize `standard` succeeded, resize `large` failed, both exports and the
    deletion succeeded -- each on the record's project and each agreeing with
    what the record kept; and no read hands a download URL a second time."""
    rows = _read_back(recorder, endpoint, owner, record)
    assert [(row["type"], row["status"]) for row in rows] == list(LIFECYCLE), [
        (row["type"], row["status"]) for row in rows
    ]
    kept = {operation["id"]: operation for operation in record["operations"]}
    for row in rows:
        assert row["project_key"] == record["project_key"], row
        assert (row["status"], row.get("error_code")) == (
            kept[row["id"]]["status"], kept[row["id"]]["error_code"],
        ), row["id"]  # fmt: skip
        assert "download_url" not in row, f"{row['id']} handed its URL again"
    _only(recorder, endpoint)


def test_the_refused_resize_changed_nothing(
    recorder: Recorder, endpoint: str, owner: str, record: dict[str, Any]
) -> None:
    """LIFE-LIVE-001, D2160: the `large` resize failed `capacity_exhausted`
    with admission as its reason, after the `standard` one succeeded -- and the
    profile the customer read after the refusal was still `standard`."""
    rows = _read_back(recorder, endpoint, owner, record)
    resizes = [row for row in rows if row["type"] == "project.resize"]
    assert [row["status"] for row in resizes] == ["succeeded", "failed"], resizes
    served, refused = resizes
    assert (served.get("result") or {}).get("profile") == "standard", served.get("result")
    assert refused.get("error_code") == "capacity_exhausted", refused
    assert (refused.get("result") or {}).get("reason") == "admission", refused.get("result")
    assert "profile" not in (refused.get("result") or {}), refused.get("result")
    assert record["observations"].get("profile_after_refused_resize") == "standard"
    _only(recorder, endpoint)


def test_the_second_creation_was_refused_without_a_row(
    recorder: Recorder,
    endpoint: str,
    owner: str,
    probe: dict[str, Any],
    record: dict[str, Any],
) -> None:
    """LIFE-LIVE-001, D2145, D2160: the lifecycle's second creation exited 5
    on `capacity_exhausted` with the organisation's creations unchanged; asked
    again now, a creation is refused `capacity_exhausted` (`no_slot`) and the
    organisation still holds exactly the one creation the record names -- the
    slot is consumed and never reissued."""
    second = record["observations"]["second_create"]
    assert (second["exit"], second["no_slot"]) == (5, True), second
    assert second["creations_before"] == second["creations_after"], second
    organization = probe["organization_id"]
    status, body = recorder.json("POST", f"{endpoint}/projects", {
        "organization_id": organization, "name": "Lifecycle s38 again", "profile": "small",
        "admin_username": "again.admin", "handoff_sha256": "0" * 64,
    }, owner)  # fmt: skip
    assert (status, body.get("error"), body.get("reason")) == (
        409, "capacity_exhausted", "no_slot",
    ), (status, body)  # fmt: skip
    status, listed = recorder.json(
        "GET", f"{endpoint}/operations?organization={organization}", None, owner
    )
    assert status == 200, status
    creations = [row["id"] for row in listed["operations"] if row["type"] == "project.create"]
    recorded = [o["id"] for o in record["operations"] if o["type"] == "project.create"]
    assert creations == recorded and len(creations) == 1, (creations, recorded)
    _only(recorder, endpoint)


def test_the_creator_claimed_the_project(
    recorder: Recorder, endpoint: str, owner: str, record: dict[str, Any]
) -> None:
    """LIFE-LIVE-002, ADR 0260: the creation's result names the project the
    record claimed, and through the slot's own door the claimed administrator
    signed in (`/auth/login` 200) and read `/auth/me` (200) with the password
    the customer chose -- a password the control plane never held."""
    rows = _read_back(recorder, endpoint, owner, record)
    created = rows[0]
    assert created["type"] == "project.create", created
    assert (created.get("result") or {}).get("project_key") == record["project_key"], created
    assert record["observations"].get("administrator") == {"login": 200, "me": 200}
    _only(recorder, endpoint)


def test_a_sleeping_and_a_deleted_project_answer_the_edges_404(
    recorder: Recorder, record: dict[str, Any]
) -> None:
    """LIFE-LIVE-002, ADR 0259: while the project slept every sample of its
    address was 404 (the edge's: no router), after `wake` it answered again
    (401 without a token), after the deletion the samples were 404 -- and
    asked now, the slot's address is the edge's own 404 page."""
    asleep = record["observations"]["asleep_samples"]
    assert set(asleep) == {"404"} and asleep["404"] >= 30, asleep
    woke = record["observations"]["wake_first_answer"]
    assert woke.get("seconds") is not None and woke.get("status") == 401, woke
    deleted = record["observations"]["deleted_samples"]
    assert set(deleted) == {"404"}, deleted
    app = str(record["app_route"]).rstrip("/")
    status, raw = recorder.send("GET", f"{app}/auth/me")
    assert (status, raw.strip()) == (404, EDGE_404), (status, raw[:80])
    _only(recorder, app)


def test_the_export_holds_only_the_customer_schemas(
    recorder: Recorder, endpoint: str, owner: str, record: dict[str, Any]
) -> None:
    """LIFE-LIVE-002, ADR 0259, D2164: the archive the customer downloaded
    lists the schemas `api` and `app` and names no `app_private`; it was
    written 0600 and its SHA-256 is the one the operation recorded; a second
    read of the operation handed no URL; and the second export's URL answered
    200 at once and 403 after its expiry."""
    schemas = record["observations"]["archive_schemas"]
    assert schemas == {"pg_restore": 0, "schemas": ["api", "app"], "app_private": False}, schemas
    exported = record["observations"]["export"]
    assert exported["mode"] == "0o600" and exported["second_read_handed_a_url"] is False, exported
    rows = _read_back(recorder, endpoint, owner, record)
    hashes = [(row.get("result") or {}).get("sha256") for row in rows
              if row["type"] == "project.export"]  # fmt: skip
    assert exported["sha256"] in hashes, (exported["sha256"], hashes)
    url_life = record["observations"]["export_url"]
    assert (url_life["at_once"], url_life["after_expiry"]) == (200, 403), url_life
    assert url_life["waited_seconds"] > 900, url_life
    _only(recorder, endpoint)
