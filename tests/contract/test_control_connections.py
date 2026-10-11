"""A project's public doors and its customer credentials through `/v1`, against a
real cluster (Session 39; D2351, D2330, ADR 0268, ADR 0269).

`GET /v1/projects/{key}/connections` serves what the registry recorded from
the deployed document -- the two doors and a snippet per measured client,
never a password -- and `not_available` naming `pooled_endpoint` for a project
without them. `POST /v1/projects/{key}/credentials` records a
`credential.rotate` whose arguments are a role and a SCRAM verifier, for a
PERSON who is member and above; a key, a viewer, a password-shaped body and a
project without doors are each refused before a row exists.

`credential.rotate`'s row is `planned` in the ledger until Run 9, so the route
answers `not_available` in the product; these proofs accept the executed types
for their own duration (`accepting`), as `test_control_projects` does, and one
proof reads the refusal without it. The reconciler's half is played by the
superuser calling the set's invoker functions.
"""

# ruff: noqa: S608 -- every interpolated value is a uuid, a key or a document
# this module wrote, run against a throwaway cluster.

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from typing import Any

import control_cluster as cc
import pytest

from app import connection_snippets, control_service, operations

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]


def scram_verifier(password: str) -> str:
    """RFC 5802/7677's server verifier, as PostgreSQL stores one: 4096
    iterations, a 16-byte salt -- the computation the customer's CLI makes
    (ADR 0269), so only this ever leaves the workstation."""
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 4096)
    client_key = hmac.new(salted, b"Client Key", "sha256").digest()
    stored = hashlib.sha256(client_key).digest()
    server = hmac.new(salted, b"Server Key", "sha256").digest()

    def b64(value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")

    return f"SCRAM-SHA-256$4096:{b64(salt)}${b64(stored)}:{b64(server)}"


def doors(key: str) -> dict[str, Any]:
    stem = key.replace("-", "_")
    return {
        "enabled": True,
        "pooled": {
            "host": f"pool.{key}.example.com", "port": 5432, "user": f"{stem}_customer_app",
            "database": stem, "sslmode": "verify-full", "connection_limit": 2,
        },
        "direct": {
            "host": f"direct.{key}.example.com", "port": 5432, "user": f"{stem}_customer_admin",
            "database": stem, "sslmode": "verify-full", "connection_limit": 2,
        },
    }  # fmt: skip


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Any:
    try:
        with cc.control_cluster() as cluster:
            with cc.control_app(cluster, tmp_path_factory.mktemp("control-doors")) as driver:
                yield driver
    except RuntimeError as exc:
        pytest.skip(str(exc))


@pytest.fixture
def accepting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every executed type accepted, for this proof only (the gate itself is
    `test_operation_types`' and the last proof below)."""
    monkeypatch.setattr(operations, "ACCEPTED_TYPES", operations.EXECUTED_TYPES)


def _adopt(drive: Any, organization: str, endpoints: dict[str, Any] | str | None) -> str:
    """A project adopted the way `control.sh adopt` adopts one: `endpoints` as
    the document's `database.public`, or not named at all (`"absent"`)."""
    key = f"d{uuid.uuid4().hex[:8]}-prod"
    named = "" if endpoints == "absent" else f", p_endpoints => {_jsonb(endpoints)}"
    drive.cluster.query(
        f"SELECT app.control_adopt_project('{key}', '{organization}', '{key[:9]}', 'prod', "
        f"'{key}.test', '1.17.0', 'abc'{named})"
    )
    return key


def _jsonb(value: Any) -> str:
    return "NULL" if value is None else f"'{json.dumps(value)}'::jsonb"


def _org(drive: Any, label: str, endpoints: Any = "doors") -> dict[str, Any]:
    tag = f"{label}-{uuid.uuid4().hex[:6]}"
    people: dict[str, Any] = {"tokens": {}}
    owner = drive.account(f"{tag}-owner")
    people["id"] = drive.organization(owner, tag)
    people["tokens"]["owner"] = drive.token(f"{tag}-owner", drive.enable_factor(owner))
    for role in ("member", "viewer"):
        user = drive.account(f"{tag}-{role}")
        drive.member(people["id"], user, role)
        people["tokens"][role] = drive.token(f"{tag}-{role}")
    if endpoints == "doors":
        key = f"d{uuid.uuid4().hex[:8]}-prod"
        drive.cluster.query(
            f"SELECT app.control_adopt_project('{key}', '{people['id']}', '{key[:9]}', 'prod', "
            f"'{key}.test', '1.17.0', 'abc', p_endpoints => {_jsonb(doors(key))})"
        )
        people["project"] = key
    else:
        people["project"] = _adopt(drive, people["id"], endpoints)
    return people


def _key(drive: Any, org: dict[str, Any], scopes: list[str]) -> str:
    minted = drive.call(
        "POST", f"/v1/organizations/{org['id']}/keys", token=org["tokens"]["member"],
        body={"name": "automation", "scopes": scopes},
    )  # fmt: skip
    assert minted.status_code == 201, minted.text
    return minted.json()["key"]


def _rows(drive: Any, key: str) -> int:
    return int(
        drive.cluster.query(
            f"SELECT count(*) FROM app.control_operations WHERE project_key = '{key}'"
        )[0]
    )


NOT_AVAILABLE = {"error": "not_available", "ledger_row": "pooled_endpoint"}


# ---------------------------------------------------------------------------
# GET /v1/projects/{key}/connections
# ---------------------------------------------------------------------------


def test_a_viewer_reads_the_two_doors_and_no_password(drive: Any) -> None:
    org = _org(drive, "read")
    key = org["project"]
    path = f"/v1/projects/{key}/connections"
    answered = drive.call("GET", path, token=org["tokens"]["viewer"])
    assert answered.status_code == 200, answered.text
    body = answered.json()
    recorded = doors(key)
    assert set(body) == {"project", "pooled", "direct", "password", "snippets"}
    assert body["project"] == key
    for door in ("pooled", "direct"):
        assert body[door] == {m: recorded[door][m] for m in control_service.DOOR_MEMBERS}
    assert body["password"] == connection_snippets.PASSWORD_PLACEHOLDER
    assert body["snippets"] == connection_snippets.snippets(recorded)
    assert answered.headers["cache-control"] == "no-store"

    # A key that reads projects reads them; one that does not, does not.
    reader = _key(drive, org, ["projects:read"])
    assert drive.call("GET", path, token=reader).json() == body
    other = _key(drive, org, ["operations:read"])
    assert drive.call("GET", path, token=other).status_code == 403
    # A foreign organisation's member: the one `not_found`.
    stranger = _org(drive, "stranger")
    foreign = drive.call("GET", path, token=stranger["tokens"]["owner"])
    assert (foreign.status_code, foreign.json()) == (404, {"error": "not_found"})


@pytest.mark.parametrize(
    "endpoints",
    ["absent", None, {"enabled": False, "pooled": None, "direct": None}],
    ids=["never-recorded", "null", "disabled"],
)
def test_a_project_without_doors_is_not_available(drive: Any, endpoints: Any) -> None:
    org = _org(drive, "nodoors", endpoints)
    answered = drive.call(
        "GET", f"/v1/projects/{org['project']}/connections", token=org["tokens"]["viewer"]
    )
    assert (answered.status_code, answered.json()) == (409, NOT_AVAILABLE)


def test_a_readoption_keeps_unnamed_doors_and_replaces_named_ones(drive: Any) -> None:
    """D2351: an operator's adoption from a document that carries no
    `database.public` never erases the doors the reconciler recorded; one that
    carries them replaces them whole."""
    org = _org(drive, "readopt")
    key = org["project"]
    path = f"/v1/projects/{key}/connections"
    drive.cluster.query(
        f"SELECT app.control_adopt_project('{key}', '{org['id']}', '{key[:9]}', 'prod', "
        f"'{key}.test', '1.17.0', 'def')"
    )
    assert drive.call("GET", path, token=org["tokens"]["viewer"]).status_code == 200
    drive.cluster.query(
        f"SELECT app.control_adopt_project('{key}', '{org['id']}', '{key[:9]}', 'prod', "
        f"'{key}.test', '1.17.0', 'def', p_endpoints => "
        f"{_jsonb({'enabled': False, 'pooled': None, 'direct': None})})"
    )
    answered = drive.call("GET", path, token=org["tokens"]["viewer"])
    assert (answered.status_code, answered.json()) == (409, NOT_AVAILABLE)


# ---------------------------------------------------------------------------
# POST /v1/projects/{key}/credentials
# ---------------------------------------------------------------------------


def test_a_member_requests_a_rotation_by_its_verifier_alone(drive: Any, accepting: None) -> None:
    org = _org(drive, "rotate")
    key = org["project"]
    verifier = scram_verifier(secrets.token_urlsafe(32))
    answered = drive.call(
        "POST", f"/v1/projects/{key}/credentials", token=org["tokens"]["member"],
        body={"role": "customer_app", "verifier": verifier},
    )  # fmt: skip
    assert answered.status_code == 202, answered.text
    operation = answered.json()["operation"]
    assert (operation["type"], operation["status"], operation["project_key"]) == (
        "credential.rotate",
        "pending",
        key,
    )
    (arguments,) = drive.cluster.query(
        f"SELECT arguments FROM app.control_operations WHERE id = '{operation['id']}'"
    )
    assert json.loads(arguments) == {"role": "customer_app", "verifier": verifier}

    # The reconciler's finish: the role is declared, the verifier is not.
    (claimed,) = drive.cluster.query("SELECT id FROM app.control_claim_operation('test')")
    # As the superuser, the reconciler's own identity (the function is granted
    # to nobody else).
    refused = drive.cluster.run(
        f"SELECT app.control_finish_operation('{claimed}', 'succeeded', NULL, "
        f"{_jsonb({'role': 'customer_app', 'verifier': verifier})})"
    )
    assert refused.returncode != 0 and "AP422: undeclared_result" in refused.stderr
    drive.cluster.query(
        f"SELECT app.control_finish_operation('{claimed}', 'succeeded', NULL, "
        f"{_jsonb({'role': 'customer_app'})})"
    )
    read = drive.call("GET", f"/v1/operations/{claimed}", token=org["tokens"]["member"])
    assert read.json()["result"] == {"role": "customer_app"}


def test_a_resize_may_record_its_admission_reading(drive: Any, accepting: None) -> None:
    """D2362: `control_result_members` lets a resize carry `admission`."""
    org = _org(drive, "admission")
    put = drive.call(
        "PUT", f"/v1/projects/{org['project']}/compute", token=org["tokens"]["member"],
        body={"profile": "large"},
    )  # fmt: skip
    assert put.status_code == 202, put.text
    (claimed,) = drive.cluster.query("SELECT id FROM app.control_claim_operation('test')")
    reading = {"requested_mb": 840, "safe_available_mb": 4600}
    drive.cluster.query(
        f"SELECT app.control_finish_operation('{claimed}', 'succeeded', NULL, "
        f"{_jsonb({'profile': 'large', 'admission': reading})})"
    )
    read = drive.call("GET", f"/v1/operations/{claimed}", token=org["tokens"]["member"])
    assert read.json()["result"]["admission"] == reading


@pytest.mark.parametrize(
    "body",
    [
        {"role": "customer_app", "verifier": "hunter2"},
        {"role": "customer_app", "verifier": "md5" + "0" * 32},
        {"role": "customer_app"},
        {"role": "postgres", "verifier": "VERIFIER"},
        {"role": "customer_app", "verifier": "VERIFIER", "password": "hunter2"},
        {"role": "customer_app", "password": "hunter2"},
    ],
)
def test_a_body_that_is_not_one_verifier_is_refused_before_a_row(
    drive: Any, accepting: None, body: dict[str, Any]
) -> None:
    org = _org(drive, "malformed")
    verifier = scram_verifier("not the customer's")
    sent = {k: (verifier if v == "VERIFIER" else v) for k, v in body.items()}
    answered = drive.call(
        "POST", f"/v1/projects/{org['project']}/credentials", token=org["tokens"]["member"],
        body=sent,
    )  # fmt: skip
    assert answered.status_code == 400, answered.text
    assert _rows(drive, org["project"]) == 0


def test_only_a_person_who_is_member_may_rotate_and_only_with_doors(
    drive: Any, accepting: None
) -> None:
    org = _org(drive, "who")
    path = f"/v1/projects/{org['project']}/credentials"
    body = {"role": "customer_admin", "verifier": scram_verifier("x")}
    viewer = drive.call("POST", path, token=org["tokens"]["viewer"], body=body)
    assert (viewer.status_code, viewer.json()) == (403, {"error": "authorization_failed"})
    key = _key(drive, org, ["projects:read", "projects:write"])
    by_key = drive.call("POST", path, token=key, body=body)
    assert (by_key.status_code, by_key.json()) == (403, {"error": "human_session_required"})
    assert _rows(drive, org["project"]) == 0

    bare = _org(drive, "bare", "absent")
    without = drive.call(
        "POST", f"/v1/projects/{bare['project']}/credentials", token=bare["tokens"]["member"],
        body=body,
    )  # fmt: skip
    assert (without.status_code, without.json()) == (409, NOT_AVAILABLE)
    assert _rows(drive, bare["project"]) == 0

    # Control: the member, on the project with doors.
    assert drive.call("POST", path, token=org["tokens"]["member"], body=body).status_code == 202


def test_the_rotation_is_not_offered_until_its_row_is(
    drive: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`credential.rotate` withdrawn from the accepted set -- as it was while
    `direct_endpoint` was `planned`, and will be if the close returns the row --
    and the route answers `not_available` naming the row, before the body is
    read. (Since Session 39's Run 9 the committed set accepts it.)"""
    monkeypatch.setattr(
        operations, "ACCEPTED_TYPES", operations.EXECUTED_TYPES - {"credential.rotate"}
    )
    org = _org(drive, "planned")
    answered = drive.call(
        "POST", f"/v1/projects/{org['project']}/credentials", token=org["tokens"]["member"],
        body={"role": "customer_app", "verifier": scram_verifier("y")},
    )  # fmt: skip
    assert (answered.status_code, answered.json()) == (
        409,
        {"error": "not_available", "ledger_row": "direct_endpoint"},
    )
    assert _rows(drive, org["project"]) == 0
