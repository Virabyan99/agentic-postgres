"""Session 46's journey: a membership link to a project made, connected, queried and read.

`JRN-001` (claim `journey_live`), `CON-CREATE-002` (`console_create_live`) and
`CTL-DIAG-002` (`support_bundle_live`) -- ADR 0290 §9, ADR 0291, ADR 0292,
D2871-D2874. Run from the workstation after the trip's journey (Run 7's
launcher): `tests/external/browser/journey_walk.py` drove a real Chromium from a
membership invitation link the probe owner minted to a project created in the
console on `slot11-prod`, and wrote ONE record (`APG_JOURNEY_RECORD_FILE`, 0600)
-- step codes and times, origins, statuses, the bundle's verdicts and ages,
never a password, seed, token or cookie value (its self-check refuses one) --
with the four secrets a later step needs in 0600 files beside it. The lifecycle
then continued from that creation (`--from-journey`, D2872) and deleted the
project, so **J14 and the creation's identity are read from the lifecycle
record** (`APG_LIFECYCLE_RECORD_FILE`), and the bundle from what the browser
read while the project lived. **J9 -- the string connects -- is read while the
project lives too** (D2945): Run 9's live J9 ran after the deletion and could
only fail (D2940 (4)), so the trip's launcher calls `read_the_string` (this
module's own `_connect`) right after the driver exits and writes its reading
beside the record; J9 and `test_the_string_connected` read that file, bounded
by J8 and the lifecycle's deletion.

The reading of the journey record is `journey_record.problems`, the one the
driver itself ran (JRN-002 holds it offline). **No SSH, no process door**
(D2174). Run 9 executed these proofs once (D2940): all passed but the two
connections.
"""

# ruff: noqa: F811 -- the imported names are pytest fixtures.

from __future__ import annotations

import ast
import json
import os
import re
import stat
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import psycopg
import pytest
from tests.external.browser import journey_record
from tests.external.redaction import Secret
from tests.external.test_session38_public_lifecycle import control, endpoint  # noqa: F401
from tests.external.test_session39_public_endpoints import ROOTS

from agentic_postgres import naming

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment(
        "APG_CONTROL_OUTPUTS", "APG_JOURNEY_RECORD_FILE", "APG_LIFECYCLE_RECORD_FILE"
    ),
]

SITE = "https://agenticpostgresql.com"
USER_AGENT = "agentic-postgres-proof"  # D2728
DIGEST_META = re.compile(r'<meta name="apg-site-digest" content="([0-9a-f]{64})">')
#: A host path in a bundle's detail (the reduction replaces one, D2897).
HOST_PATH = re.compile(r"(?<![\w:/.])/(?:[\w.@+-]+/)*[\w.@+-]+")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")


def _private(path: Path) -> Path:
    assert stat.S_IMODE(path.stat().st_mode) == 0o600, f"{path} is not 0600"
    return path


@pytest.fixture(scope="module")
def journey(control: dict[str, Any], endpoint: str) -> dict[str, Any]:
    """The journey's record: private, live, Session 46's, at the console's
    origin, about the deployed commit, not a dry run's, and clean by the
    reading the driver ran."""
    path = _private(Path(os.environ.get("APG_JOURNEY_RECORD_FILE", "")))
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document.get("mode") == "live", document.get("mode")
    assert document.get("base") == naming.console_origin(str(urlsplit(endpoint).hostname))
    assert document.get("source_commit") == control["source_commit"], (
        document.get("source_commit"), control["source_commit"],
    )  # fmt: skip
    assert journey_record.problems(document) == [], journey_record.problems(document)
    document["_directory"] = str(path.parent)
    return document


@pytest.fixture(scope="module")
def lifecycle() -> dict[str, Any]:
    path = _private(Path(os.environ.get("APG_LIFECYCLE_RECORD_FILE", "")))
    return json.loads(path.read_text(encoding="utf-8"))


def instant(text: str) -> datetime:
    return datetime.fromisoformat(str(text).replace("Z", "+00:00"))


def _beside(journey: dict[str, Any], member: str) -> Path:
    return _private(Path(journey["_directory"]) / str(journey[member]))


def _step(journey: dict[str, Any], code: str) -> dict[str, Any]:
    (entry,) = [step for step in journey["steps"] if step["step"] == code]
    assert entry["outcome"] == "ok", entry
    return entry


def _connect(journey: dict[str, Any]) -> Any:
    string = journey["string"]
    password = Secret(_beside(journey, "password_file").read_text(encoding="utf-8").strip("\n"))
    return psycopg.connect(
        host=string["host"], port=string["port"], dbname=string["database"],
        user=string["user"], password=password, sslmode="verify-full",
        sslrootcert=str(ROOTS), connect_timeout=15, autocommit=True,
    )  # fmt: skip


def read_the_string(journey: dict[str, Any]) -> dict[str, Any]:
    """J9's reading, taken by `_connect` itself from this workstation while the
    project lives -- right after the driver exits, before the lifecycle that
    continues the creation deletes it (D2940 (4), D2945). The trip's launcher
    calls this and writes what it returns, 0600, as `journey_record.CONNECTED_FILE`
    beside the record; the two proofs below read that file."""
    string = journey["string"]
    with _connect(journey) as connection:
        info = connection.info
        return {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "host": string["host"], "port": string["port"],
            "database": string["database"], "user": string["user"],
            "sslmode": "verify-full", "sslrootcert": str(ROOTS),
            "select_1": list(connection.execute("select 1").fetchone()),
            "current_user": connection.execute("select current_user").fetchone()[0],
            "ssl_in_use": bool(info.pgconn.ssl_in_use),
        }  # fmt: skip


def _connected(journey: dict[str, Any], lifecycle: dict[str, Any]) -> dict[str, Any]:
    """J9's reading, beside the record: about this record's string, verified
    against the system roots, taken after Connect showed the string (J8) and
    before the lifecycle asked for the project's deletion."""
    path = _private(Path(journey["_directory"]) / journey_record.CONNECTED_FILE)
    reading = json.loads(path.read_text(encoding="utf-8"))
    string = journey["string"]
    assert [reading[k] for k in ("host", "port", "database", "user")] == [
        string[k] for k in ("host", "port", "database", "user")
    ], reading
    assert (reading["sslmode"], reading["sslrootcert"], reading["ssl_in_use"]) == (
        "verify-full", str(ROOTS), True,
    ), reading  # fmt: skip
    deletions = [o for o in lifecycle["operations"] if o["type"] == "project.delete"]
    assert deletions, "the lifecycle recorded no deletion to bound the reading by"
    assert instant(_step(journey, "j08")["at"]) <= instant(reading["at"]), reading["at"]
    assert instant(reading["at"]) < instant(deletions[0]["created_at"]), (
        reading["at"], deletions[0]["created_at"],
    )  # fmt: skip
    return reading


# ---------------------------------------------------------------------------
# JRN-001: J1-J14
# ---------------------------------------------------------------------------


def test_j01_the_invitation_link_opened_the_console(journey: dict[str, Any]) -> None:
    """The link opened the console's *Create your account*, its token left the
    address bar, and the site's digest was read from the published page --
    the site the journey followed is the site published now."""
    _step(journey, "j01")
    assert journey.get("address_bar_clean") is True
    request = urllib.request.Request(  # noqa: S310 -- the site's own name, https
        f"{SITE}/", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 -- the site's name
        published = DIGEST_META.search(response.read().decode("utf-8"))
    assert published and published.group(1) == journey["site_digest"]


def test_j02_the_account_was_made(journey: dict[str, Any]) -> None:
    _step(journey, "j02")
    assert str(journey.get("account", "")).startswith("journey-s46-"), journey.get("account")


def test_j03_the_overview_named_the_organisation_it_joined(journey: dict[str, Any]) -> None:
    _step(journey, "j03")
    assert any("probe-s37" in named for named in journey["joined"]), journey["joined"]


def test_j04_a_new_organisation_was_made(journey: dict[str, Any]) -> None:
    _step(journey, "j04")
    assert re.fullmatch(r"[0-9a-f-]{36}", journey["organization"]), journey["organization"]
    assert journey["organization_name"] == "lifecycle-s46"


def test_j05_the_owners_factor_was_enrolled(journey: dict[str, Any]) -> None:
    """The owner's factor, from the page's own text, kept 0600 for the
    lifecycle's sign-in as this account (D2872)."""
    _step(journey, "j05")
    assert _beside(journey, "seed_file").read_text(encoding="utf-8").strip()
    assert _beside(journey, "account_password_file").read_text(encoding="utf-8").strip()


def test_j06_a_project_was_asked_for_in_the_console(journey: dict[str, Any]) -> None:
    _step(journey, "j06")
    assert re.fullmatch(r"[0-9a-f-]{36}", journey["operation_id"]), journey["operation_id"]


def test_j07_the_creation_succeeded(journey: dict[str, Any]) -> None:
    """Followed in the page to `succeeded`; the project is slot11-prod (D2870)."""
    _step(journey, "j07")
    assert journey["project_key"] == "slot11-prod", journey["project_key"]
    assert journey["create_seconds"] > 0


def test_j08_connect_set_a_password_and_showed_the_string(journey: dict[str, Any]) -> None:
    _step(journey, "j08")
    assert journey["string_parameters"].get("sslmode") == "verify-full"
    assert journey["string"]["holds_the_password"] is True


def test_j09_the_string_connects(journey: dict[str, Any], lifecycle: dict[str, Any]) -> None:
    """The password the page showed opens the pooled door over TLS, verified
    against the system roots -- from this workstation, while the project lived
    (D2945: the lifecycle deletes it before this half runs)."""
    assert _connected(journey, lifecycle)["select_1"] == [1]


def test_j10_the_sql_editor_answered(journey: dict[str, Any]) -> None:
    _step(journey, "j10")
    assert journey["editor_rows"] == [["1"]]


def test_j11_the_readings_rendered(journey: dict[str, Any]) -> None:
    _step(journey, "j11")
    for view in journey_record.VIEWS:
        assert journey["views"][view]["read"] is True, (view, journey["views"][view])


def test_j12_the_support_bundle_was_read(journey: dict[str, Any]) -> None:
    _step(journey, "j12")
    assert journey["support_bundle"]["said"] is True


def test_j13_signed_out(journey: dict[str, Any]) -> None:
    _step(journey, "j13")
    assert journey["cookies_after_sign_out"] == 0


def test_j14_the_project_was_deleted_and_its_names_refuse(
    journey: dict[str, Any], lifecycle: dict[str, Any]
) -> None:
    """The lifecycle that continued this creation deleted the project: its
    deletion succeeded and every sample of its address after it was the edge's
    404."""
    assert lifecycle["project_key"] == journey["project_key"]
    deletions = [o for o in lifecycle["operations"] if o["type"] == "project.delete"]
    assert deletions and deletions[-1]["status"] == "succeeded", deletions
    assert set(lifecycle["observations"]["deleted_samples"]) == {"404"}


# ---------------------------------------------------------------------------
# CON-CREATE-002: the console's creation, live
# ---------------------------------------------------------------------------


def test_the_project_was_created_in_the_console(
    journey: dict[str, Any], lifecycle: dict[str, Any]
) -> None:
    """The creation the lifecycle continued is the one the console recorded:
    the journey's operation, a `project.create` that succeeded with its key."""
    created = [o for o in lifecycle["operations"] if o["id"] == journey["operation_id"]]
    assert created and created[0]["type"] == "project.create", created
    assert created[0]["status"] == "succeeded", created[0]


def test_the_token_was_shown_once(journey: dict[str, Any]) -> None:
    """The token the panel showed is a 43-character base64url token kept 0600,
    it was gone from the page once the panel was dismissed, and the record
    holds it nowhere."""
    token = _beside(journey, "token_file").read_text(encoding="utf-8").strip()
    assert TOKEN.match(token)
    assert journey["token_gone_after_dismissal"] is True
    assert token not in json.dumps(journey)


def test_the_string_connected(journey: dict[str, Any], lifecycle: dict[str, Any]) -> None:
    assert _connected(journey, lifecycle)["current_user"] == journey["string"]["user"]


# ---------------------------------------------------------------------------
# CTL-DIAG-002: the support bundle, read as a member through the public origin
# ---------------------------------------------------------------------------


def test_the_support_bundle_lists_the_twelve_checks(journey: dict[str, Any]) -> None:
    bundle = journey["support_bundle"]
    assert bundle["checks"] == journey_record.BUNDLE_CHECKS
    ages = [int(row["age"].split()[0]) for row in bundle["rows"]]
    assert len(ages) == journey_record.BUNDLE_CHECKS and max(ages) < 1800, ages


def test_the_bundle_carries_no_host_path(journey: dict[str, Any]) -> None:
    for row in journey["support_bundle"]["rows"]:
        assert not HOST_PATH.search(row["detail"]), row["name"]


def test_this_module_uses_no_ssh() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    for needle in ("para" + "miko", '"s' + 'sh"', "ss" + "h_destination", "ss" + "h-agent"):
        assert needle not in text, needle
    imported = {
        alias.name
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "subprocess" not in imported, imported
